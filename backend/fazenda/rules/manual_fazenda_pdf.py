"""
Geração do PDF do Manual da Fazenda (server-side) — usado tanto para
download (GET /manual-fazenda/pdf) quanto para o anexo do e-mail semanal.

xhtml2pdf tem suporte CSS limitado (sem grid/flexbox/border-radius) — o
template abaixo usa só o que ele renderiza bem: tabelas, blocos com
padding/border/background-color simples. Identidade visual CowData
"Institucional" (marinho + ouro escurecido), mesma paleta de
frontend/lib/export.ts.

BUG DE SEGURANÇA CORRIGIDO (CWE-918 via CWE-80): quase todo texto que entra
neste template (nome de item de estoque, protocolo/número de animal do
calendário sanitário, responsável pelo manejo reprodutivo, sugestão
cadastrada pelo usuário) é texto livre gravável por um usuário comum — sem
gate de admin — e entrava CRU nas f-strings de HTML abaixo (`<td>{...}</td>`
etc.), sem `html.escape` nenhum. Como `gerar_pdf_manual` chama
`pisa.CreatePDF` sem `link_callback`, o xhtml2pdf busca qualquer
<img>/<link>/url(...) que encontrar no HTML — inclusive fazendo uma
requisição HTTP de verdade a partir do servidor (confirmado: o xhtml2pdf
instalado loga "Sending request for http://...” e tenta mesmo assim). Ou
seja: um nome de item de estoque como `A<img src="http://169.254.169.254/...">`
virava uma requisição SSRF disparada pelo próprio backend ao gerar o PDF.

A correção tem duas camadas independentes:
  1. `_esc()` escapa TODO texto antes de entrar no HTML — fecha a injeção na
     raiz: texto escapado nunca vira uma tag nova, então não há como um nome
     de item criar um <img>/<a> que não estava no template.
  2. `_bloquear_recursos_externos` (link_callback) garante que MESMO que uma
     tag legítima algum dia referencie uma imagem/CSS/arquivo (coisa que o
     template de hoje não faz), o xhtml2pdf nunca chega a buscar nada de
     verdade — cinto e suspensório para qualquer <img>/url(...) que passe a
     existir aqui no futuro, escapado ou não.
"""
from __future__ import annotations

import html
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


def _esc(valor) -> str:
    """Escapa QUALQUER valor antes de entrar no HTML do template — mesmo um
    campo hoje sempre numérico pode virar texto livre num refactor futuro, e
    o contrário (nome de item de estoque, protocolo sanitário, sugestão do
    usuário) já é hoje texto 100% livre gravável por qualquer usuário comum
    (ver Estoque.nome em /cadastro/estoque e /importar/produtos_estoque, sem
    gate de admin). Sem isto, um nome como `<img src=http://169.254.169.254/>`
    virava HTML de verdade dentro do `<td>{...}</td>` e o xhtml2pdf ia atrás
    do <img> — SSRF disparado pelo próprio backend (ver docstring do
    módulo)."""
    if valor is None:
        return "—"
    return html.escape(str(valor))


def _bloco_rotina(rotina: dict) -> str:
    linhas = []
    for chave, item in (("bst", rotina.get("bst")), ("visita_reprodutiva", rotina.get("visita_reprodutiva"))):
        if not item:
            continue
        datas = " · ".join(_fmt_data(d) for d in item.get("proximas_datas", []))
        linhas.append(f"""
          <tr>
            <td style="padding:6px 8px;font-weight:bold;">{_esc(item['titulo'])}</td>
            <td style="padding:6px 8px;color:{COR_MUTED};">{_esc(datas)}</td>
          </tr>
        """)
    sanit = rotina.get("sanitario") or {}
    if sanit.get("proxima"):
        p = sanit["proxima"]
        linhas.append(f"""
          <tr>
            <td style="padding:6px 8px;font-weight:bold;">Calendário sanitário</td>
            <td style="padding:6px 8px;color:{COR_MUTED};">
              Próxima: {_esc(p['protocolo'])} — animal {_esc(p['animal'])} em {_fmt_data(p['data'])}
              {f" · {_esc(sanit['vencidas'])} vencida(s)" if sanit.get('vencidas') else ""}
            </td>
          </tr>
        """)
    compras = rotina.get("compras") or []
    if compras:
        nomes = ", ".join(f"{_esc(c['nome'])} ({_esc(c['quantidade'])}/{_esc(c['estoque_minimo'])})" for c in compras)
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
        # "Fêmeas prenhas", não "Taxa de prenhez": é inventário (% do rebanho
        # apto prenhe hoje), não a taxa formal PREG/PG ELIG do BREDSUM — mesmo
        # rótulo usado na Capa e nas demais telas que mostram este campo.
        ("Fêmeas prenhas", f"{resultado['taxa_prenhez_pct']}%" if resultado.get("taxa_prenhez_pct") is not None else "—"),
        ("Taxa de concepção", f"{resultado['taxa_concepcao_pct']}%" if resultado.get("taxa_concepcao_pct") is not None else "—"),
        ("Taxa de serviço", f"{resultado['taxa_servico_pct']}%" if resultado.get("taxa_servico_pct") is not None else "—"),
        ("Produção média (kg)", resultado.get("producao_media_kg")),
        ("Produção total/dia (kg)", resultado.get("producao_total_dia_kg")),
        ("DEL médio", resultado.get("del_medio")),
    ]
    celulas = "".join(
        f"""<td style="padding:8px;border:1px solid {COR_LINHA};text-align:center;">
              <div style="font-size:13pt;font-weight:bold;color:{COR_VINHO};">{_esc(v)}</div>
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
              <span style="font-size:7.5pt;text-transform:uppercase;color:{COR_MUTED};">{_esc(i['categoria'])}</span><br/>
              {_esc(i['texto'])}
            </td>
          </tr>
        """)
    return f"<table style='width:100%;border-collapse:collapse;'>{''.join(linhas)}</table>"


def _bloco_sugestoes(sugestoes: list[dict]) -> str:
    if not sugestoes:
        return "<p style='color:#6B7280;font-size:9pt;'>Nenhuma sugestão no momento.</p>"
    # `s['texto']` é o vetor mais direto do achado: a sugestão CADASTRADA PELO
    # USUÁRIO (SugestaoManualFazenda.texto), texto 100% livre — daí o _esc().
    itens = "".join(f"<li style='margin-bottom:4px;font-size:9pt;'>{_esc(s['texto'])}</li>" for s in sugestoes)
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
        emp = f" — {_esc(responsavel['empresa'])}" if responsavel.get("empresa") else ""
        resp_linha = f"<p style='font-size:8.5pt;color:{COR_MUTED};'>Manejo reprodutivo: {_esc(responsavel['nome'])}{emp}</p>"
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


def _bloquear_recursos_externos(uri, basepath):  # noqa: ARG001 — assinatura exigida pelo xhtml2pdf
    """`link_callback` do xhtml2pdf (ver pisa.CreatePDF abaixo): chamado toda
    vez que o parser encontra um <img src=...>, <link>, list-style-image ou
    fonte externa. Este template NUNCA referencia nenhum recurso externo de
    verdade (só texto/tabela com estilo inline) — então qualquer chamada
    aqui só pode vir de conteúdo injetado (a defesa de `_esc()` acima já
    deveria ter neutralizado, mas isto é cinto-e-suspensório) ou de alguém
    adicionar um <img> de verdade aqui no futuro sem passar por revisão de
    segurança.

    Devolve um data URI vazio/inválido em vez de `None`: o xhtml2pdf trata
    `None` como "não reescreva nada, siga com a URI original"
    (`pisaFileObject.__init__`, xhtml2pdf/files.py) — ou seja, devolver
    `None` aqui NÃO bloquearia a rede/arquivo, é só um passthrough. Só uma
    URI DIFERENTE de fato desvia a busca; "data:," falha ao decodificar
    (não tem "base64,") e o próprio xhtml2pdf captura esse erro e trata como
    "imagem não encontrada" — sem nenhuma requisição de rede ou leitura de
    arquivo local ter sido feita."""
    return "data:,"


def gerar_pdf_manual(manual: dict) -> bytes:
    buffer = BytesIO()
    pisa.CreatePDF(_html_manual(manual), dest=buffer, link_callback=_bloquear_recursos_externos)
    return buffer.getvalue()
