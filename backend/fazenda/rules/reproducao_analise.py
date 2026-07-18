"""
Análise reprodutiva — transforma os serviços em registros achatados com as
dimensões usadas nos dashboards (concepção/perda por categoria, raça, ordem
de parto/tentativa, condição de IA, inseminador, mês, DEL no serviço).

O front consome esses registros e fatia/agrega conforme os filtros escolhidos.
Métrica central: TAXA DE CONCEPÇÃO = positivos / serviços diagnosticados.
"""
from __future__ import annotations

from datetime import date


def _del_servico(data_servico, data_ult_parto) -> int | None:
    if isinstance(data_servico, date) and isinstance(data_ult_parto, date) and data_servico >= data_ult_parto:
        return (data_servico - data_ult_parto).days
    return None


def _metodo_ia(tipo_servico: str | None, protocolo: str | None) -> str:
    """
    Classifica como o serviço foi feito:
      - Inseminação artificial COM protocolo hormonal  -> 'IATF'
      - Inseminação artificial SEM protocolo (em cio)   -> 'IA em cio natural'
      - Cobertura/monta                                 -> 'Monta natural'
    """
    tipo = (tipo_servico or "").strip().lower()
    tem_protocolo = bool((protocolo or "").strip())
    if "insemin" in tipo or tipo in ("ia", "iatf"):
        return "IATF" if tem_protocolo else "IA em cio natural"
    if "cobertura" in tipo or "monta" in tipo:
        return "Monta natural"
    # Sem tipo declarado: infere pelo protocolo.
    return "IATF" if tem_protocolo else "(sem método)"


def analisar_servicos(servicos: list[dict]) -> list[dict]:
    """Achata os serviços para análise. Um registro por serviço."""
    registros: list[dict] = []
    for s in servicos:
        ds = s.get("data_servico")
        diag = (s.get("diagnostico") or "").strip().upper() or None
        diagnosticado = diag in ("POSITIVO", "NEGATIVO")
        ano = ds.year if isinstance(ds, date) else None
        mes = f"{ds.year}-{ds.month:02d}" if isinstance(ds, date) else None
        dpp = s.get("data_perda_prenhez")
        mes_perda = f"{dpp.year}-{dpp.month:02d}" if isinstance(dpp, date) else None

        registros.append({
            "numero": s.get("numero_matriz"),
            "raca": s.get("raca_matriz") or "(sem raça)",
            "categoria": s.get("categoria") or "(sem categoria)",
            "ordem_parto": s.get("ordem_parto"),
            "ordem_tentativa": s.get("ordem_tentativa"),
            "tipo_servico": s.get("tipo_servico") or "(sem tipo)",
            "protocolo": s.get("protocolo") or "(sem protocolo)",
            # 'reprodutor' na fonte é o touro/sêmen usado no serviço.
            "touro": s.get("reprodutor") or "(sem touro)",
            # Sexado/convencional/fazenda — gravado no serviço desde que essa
            # distinção passou a ser perguntada; None em registros antigos (o
            # chamador pode completar por nome via Estoque de Sêmen).
            "tipo_semen": s.get("tipo_semen"),
            "inseminador": s.get("inseminador") or "(sem inseminador)",
            "metodo_ia": _metodo_ia(s.get("tipo_servico"), s.get("protocolo")),
            "ano": ano,
            "mes": mes,
            "data": ds.isoformat() if isinstance(ds, date) else None,
            "del_servico": _del_servico(ds, s.get("data_ult_parto")),
            "diagnostico": diag,
            "diagnosticado": diagnosticado,
            "positivo": diag == "POSITIVO",
            "perda": bool(s.get("data_perda_prenhez")),
            "mes_perda": mes_perda,
            "usuario_id": s.get("usuario_id"),
        })
    return registros


# ---------------------------------------------------------------------------
# Agregação mensal — alimenta o gráfico interativo configurável de Análise
# reprodutiva (cruzamento de métricas por mês/ano). Cada série é uma lista
# alinhada 1:1 com a lista de meses retornada.
# ---------------------------------------------------------------------------
def agregar_mensal(registros: list[dict], secagens: list[dict], controles: list[dict]) -> dict:
    from collections import defaultdict

    meses: set[str] = set()
    por_mes_servico: dict[str, list[dict]] = defaultdict(list)
    for r in registros:
        if r["mes"]:
            por_mes_servico[r["mes"]].append(r)
            meses.add(r["mes"])
        if r["mes_perda"]:
            meses.add(r["mes_perda"])

    por_mes_secagem: dict[str, int] = defaultdict(int)
    for s in secagens:
        d = s.get("data_secagem")
        if isinstance(d, date):
            m = f"{d.year}-{d.month:02d}"
            por_mes_secagem[m] += 1
            meses.add(m)

    por_mes_producao: dict[str, list[float]] = defaultdict(list)
    for c in controles:
        d, kg = c.get("data_controle"), c.get("producao_kg")
        if isinstance(d, date) and kg is not None:
            m = f"{d.year}-{d.month:02d}"
            por_mes_producao[m].append(kg)
            meses.add(m)

    por_mes_perda: dict[str, int] = defaultdict(int)
    for r in registros:
        if r["mes_perda"]:
            por_mes_perda[r["mes_perda"]] += 1

    meses_ordenados = sorted(meses)

    def _por_mes(fn):
        return [fn(por_mes_servico.get(m, [])) for m in meses_ordenados]

    def _conta(pred):
        return _por_mes(lambda regs: sum(1 for r in regs if pred(r)))

    def _media(campo):
        def f(regs):
            vals = [r[campo] for r in regs if r.get(campo) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None
        return _por_mes(f)

    def _taxa_concepcao(regs):
        diag = sum(1 for r in regs if r["diagnosticado"])
        pos = sum(1 for r in regs if r["positivo"])
        return round(100 * pos / diag, 1) if diag else None

    def _delta(serie):
        if not serie:
            return []
        out = [None]
        for i in range(1, len(serie)):
            a, b = serie[i - 1], serie[i]
            out.append(round(b - a, 1) if a is not None and b is not None else None)
        return out

    del_medio = _media("del_servico")
    producao_leite = [
        round(sum(por_mes_producao[m]) / len(por_mes_producao[m]), 1) if por_mes_producao.get(m) else None
        for m in meses_ordenados
    ]

    series = {
        "num_servicos": _por_mes(len),
        "animais_inseminados": _conta(lambda r: r["tipo_servico"] != "Monta natural"),
        "num_ias": _conta(lambda r: r["metodo_ia"] in ("IA em cio natural", "IATF")),
        "num_montas_naturais": _conta(lambda r: r["metodo_ia"] == "Monta natural"),
        "num_coberturas": _conta(lambda r: any(p in r["tipo_servico"].lower() for p in ("cobertura", "monta"))),
        "num_ia_cio": _conta(lambda r: r["metodo_ia"] == "IA em cio natural"),
        "num_iatf": _conta(lambda r: r["metodo_ia"] == "IATF"),
        "qtd_positivos": _conta(lambda r: r["positivo"]),
        "qtd_negativos": _conta(lambda r: r["diagnosticado"] and not r["positivo"]),
        "animais_prenhes": _conta(lambda r: r["positivo"]),
        "taxa_concepcao": _por_mes(_taxa_concepcao),
        "perdas_prenhez": [por_mes_perda.get(m, 0) for m in meses_ordenados],
        "num_secagens": [por_mes_secagem.get(m, 0) for m in meses_ordenados],
        "del_medio": del_medio,
        "producao_leite": producao_leite,
    }
    series["variacao_del"] = _delta(del_medio)
    series["variacao_producao_leite"] = _delta(producao_leite)

    return {"meses": meses_ordenados, "series": series}
