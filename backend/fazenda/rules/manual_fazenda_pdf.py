"""
Geração do PDF do Manual da Fazenda (server-side) — usado tanto para
download (GET /manual-fazenda/pdf) quanto para o anexo do e-mail semanal.

xhtml2pdf tem suporte CSS limitado (sem grid/flexbox/border-radius) — o
template abaixo usa só o que ele renderiza bem: tabelas, blocos com
padding/border/background-color simples. Identidade visual CowData
"Institucional" (marinho + ouro escurecido), mesma paleta de
frontend/lib/export.ts.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

from xhtml2pdf import pisa

NOME_FAZENDA = "Fazenda Estreito Ponte de Pedra"
COR_VINHO = "#0E2A47"
COR_DOURADO = "#8A6D2F"
COR_MUTED = "#6B7280"
COR_LINHA = "#E5E7EB"


def _fmt_data(iso: str | None) -> str:
    if not iso:
        return "—"
    d, m, a = "", "", ""
    try:
        a, m, d = iso[:10].split("-")
    except ValueError:
        return iso
    return f"{d}/{m}/{a}"


def _bloco_rotina(rotina: dict) -> str:
    linhas = []
    for chave, item in (("bst", rotina.get("bst")), ("visita_reprodutiva", rotina.get("visita_reprodutiva"))):
        if not item:
            continue
        datas = " · ".join(_fmt_data(d) for d in item.get("proximas_datas", []))
        linhas.append(f"""
          <tr>
            <td style="padding:6px 8px;font-weight:bold;">{item['titulo']}</td>
            <td style="padding:6px 8px;color:{COR_MUTED};">{datas}</td>
          </tr>
        """)
    sanit = rotina.get("sanitario") or {}
    if sanit.get("proxima"):
        p = sanit["proxima"]
        linhas.append(f"""
          <tr>
            <td style="padding:6px 8px;font-weight:bold;">Calendário sanitário</td>
            <td style="padding:6px 8px;color:{COR_MUTED};">
              Próxima: {p['protocolo']} — animal {p['animal']} em {_fmt_data(p['data'])}
              {f" · {sanit['vencidas']} vencida(s)" if sanit.get('vencidas') else ""}
            </td>
          </tr>
        """)
    compras = rotina.get("compras") or []
    if compras:
        nomes = ", ".join(f"{c['nome']} ({c['quantidade']}/{c['estoque_minimo']})" for c in compras)
        linhas.append(f"""
          <tr>
            <td style="padding:6px 8px;font-weight:bold;">Compras recorrentes</td>
            <td style="padding:6px 8px;color:{COR_MUTED};">{nomes}</td>
          </tr>
        """)
    if not linhas:
        return "<p style='color:#6B7280;font-size:9pt;'>Nenhuma rotina automática configurada ainda.</p>"
    return f"<table style='width:100%;border-collapse:collapse;font-size:9pt;'>{''.join(linhas)}</table>"


def _bloco_resultado(resultado: dict) -> str:
    itens = [
        ("Total de animais", resultado.get("total_animais")),
        ("Vacas em lactação", resultado.get("vacas_lactacao")),
        ("Taxa de prenhez", f"{resultado['taxa_prenhez_pct']}%" if resultado.get("taxa_prenhez_pct") is not None else "—"),
        ("Taxa de concepção", f"{resultado['taxa_concepcao_pct']}%" if resultado.get("taxa_concepcao_pct") is not None else "—"),
        ("Taxa de serviço", f"{resultado['taxa_servico_pct']}%" if resultado.get("taxa_servico_pct") is not None else "—"),
        ("Produção média (kg)", resultado.get("producao_media_kg")),
        ("Produção total/dia (kg)", resultado.get("producao_total_dia_kg")),
        ("DEL médio", resultado.get("del_medio")),
    ]
    celulas = "".join(
        f"""<td style="padding:8px;border:1px solid {COR_LINHA};text-align:center;">
              <div style="font-size:13pt;font-weight:bold;color:{COR_VINHO};">{v if v is not None else "—"}</div>
              <div style="font-size:7.5pt;color:{COR_MUTED};">{label}</div>
            </td>"""
        for label, v in itens
    )
    return f"<table style='width:100%;border-collapse:collapse;'><tr>{celulas}</tr></table>"


def _bloco_insights(insights: list[dict]) -> str:
    if not insights:
        return "<p style='color:#6B7280;font-size:9pt;'>Sem histórico suficiente para gerar insights ainda.</p>"
    linhas = []
    for i in insights:
        cor = "#4A7A4E" if i["tendencia"] == "alta" else "#B3781F"
        seta = "&#8593;" if i["tendencia"] == "alta" else "&#8595;"
        linhas.append(f"""
          <tr>
            <td style="padding:6px 8px;width:24px;font-weight:bold;color:{cor};">{seta}</td>
            <td style="padding:6px 8px;font-size:9pt;">
              <span style="font-size:7.5pt;text-transform:uppercase;color:{COR_MUTED};">{i['categoria']}</span><br/>
              {i['texto']}
            </td>
          </tr>
        """)
    return f"<table style='width:100%;border-collapse:collapse;'>{''.join(linhas)}</table>"


def _bloco_sugestoes(sugestoes: list[dict]) -> str:
    if not sugestoes:
        return "<p style='color:#6B7280;font-size:9pt;'>Nenhuma sugestão no momento.</p>"
    itens = "".join(f"<li style='margin-bottom:4px;font-size:9pt;'>{s['texto']}</li>" for s in sugestoes)
    return f"<ul style='padding-left:16px;margin:0;'>{itens}</ul>"


def _titulo_secao(texto: str) -> str:
    return f"""
      <div style="margin:18px 0 8px;padding-bottom:4px;border-bottom:1px solid {COR_DOURADO};">
        <span style="font-size:11pt;font-weight:bold;color:{COR_VINHO};">{texto}</span>
      </div>
    """


def _html_manual(manual: dict) -> str:
    hoje = date.today().strftime("%d/%m/%Y")
    responsavel = manual.get("responsavel_manejo") or {}
    resp_linha = ""
    if responsavel.get("nome"):
        emp = f" — {responsavel['empresa']}" if responsavel.get("empresa") else ""
        resp_linha = f"<p style='font-size:8.5pt;color:{COR_MUTED};'>Manejo reprodutivo: {responsavel['nome']}{emp}</p>"
    return f"""
    <html>
    <head><meta charset="utf-8" /></head>
    <body style="font-family:Helvetica,Arial,sans-serif;color:#201512;">
      <div style="border-bottom:2px solid {COR_VINHO};padding-bottom:8px;margin-bottom:12px;">
        <span style="font-size:8pt;letter-spacing:1px;color:{COR_MUTED};">{NOME_FAZENDA.upper()}</span><br/>
        <span style="font-size:16pt;font-weight:bold;color:{COR_VINHO};">Manual da Fazenda</span><br/>
        <span style="font-size:8pt;color:{COR_MUTED};">Gerado em {hoje}</span>
        {resp_linha}
      </div>

      {_titulo_secao("Sua rotina")}
      {_bloco_rotina(manual.get("rotina") or {})}

      {_titulo_secao("Resultado")}
      {_bloco_resultado(manual.get("resultado") or {})}

      {_titulo_secao("Insights")}
      {_bloco_insights(manual.get("insights") or [])}

      {_titulo_secao("Preditivo e sugestões")}
      {_bloco_sugestoes(manual.get("sugestoes") or [])}
    </body>
    </html>
    """


def gerar_pdf_manual(manual: dict) -> bytes:
    buffer = BytesIO()
    pisa.CreatePDF(_html_manual(manual), dest=buffer)
    return buffer.getvalue()
