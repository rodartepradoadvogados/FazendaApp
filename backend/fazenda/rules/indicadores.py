"""
Indicadores zootécnicos, reprodutivos e produtivos do rebanho.

Funções puras: recebem listas de dicts (Animal, Servico, Parto — já em model_dump)
e devolvem um dicionário de indicadores. Sem acesso a banco, testáveis isoladamente.

Referências de negócio (Seção 5 do CONTEXTO_PROJETO_FAZENDA.md):
  - Lactação = grupos 01/02/03; Pré-parto = 04; Secas = 05.
  - Sit. rep.: Ges. (prenhe), Vaz.* (vazia), Ins. (inseminada).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fazenda.rules.gestation import calcular_parto_provavel
from fazenda.rules.parametros import BENCHMARK_METAS

# Códigos de grupo (2 primeiros dígitos do grupo_primario).
GRUPOS_LACTACAO = {"01", "02", "03"}
GRUPO_PRE_PARTO = "04"
GRUPO_SECAS = "05"

# Taxa de concepção considerada sempre a partir desta data.
CONCEPCAO_DESDE = date(2026, 1, 1)

# Piso biológico do intervalo entre partos (IEP).
# Uma nova cria exige, no mínimo, a gestação (~9 meses) somada ao período de
# espera voluntária (PEV) até a matriz emprenhar de novo. Dois registros de
# parto mais próximos que isso são o mesmo evento (duplicidade na fonte) e não
# representam um intervalo real — são descartados para não distorcer a média.
GESTACAO_MINIMA_DIAS = 280  # Holandês (menor gestação entre as raças)
PEV_DIAS = 45               # período de espera voluntária mínimo
IEP_MINIMO_DIAS = GESTACAO_MINIMA_DIAS + PEV_DIAS  # 325 dias (~10,7 meses)


def _codigo_grupo(grupo: Optional[str]) -> Optional[str]:
    """Extrai o código de 2 dígitos do início do grupo (ex.: '01 - NOV. ALTA' -> '01')."""
    if not grupo:
        return None
    g = grupo.strip()
    if len(g) >= 2 and g[:2].isdigit():
        return g[:2]
    return None


def _media(valores: list[float]) -> Optional[float]:
    vals = [v for v in valores if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _diag_upper(s: str | None) -> str:
    return (s or "").strip().upper()


def _no_periodo(s: dict) -> bool:
    ds = s.get("data_servico")
    return isinstance(ds, date) and ds >= CONCEPCAO_DESDE


def _del_serv(s: dict) -> Optional[float]:
    d = s.get("del_servico")
    if isinstance(d, (int, float)) and d >= 0:
        return float(d)
    ds, dp = s.get("data_servico"), s.get("data_ult_parto")
    if isinstance(ds, date) and isinstance(dp, date) and ds >= dp:
        return float((ds - dp).days)
    return None


def _iep_dias(partos: list[dict]) -> Optional[int]:
    por_matriz: dict[str, list[date]] = {}
    for p in partos:
        d = p.get("data_parto")
        m = p.get("numero_matriz")
        if d and m:
            por_matriz.setdefault(m, []).append(d)
    intervalos: list[int] = []
    for datas in por_matriz.values():
        distintos: list[date] = []
        for d in sorted(set(datas)):
            if not distintos or (d - distintos[-1]).days >= IEP_MINIMO_DIAS:
                distintos.append(d)
        for ant, atu in zip(distintos, distintos[1:]):
            intervalos.append((atu - ant).days)
    return round(sum(intervalos) / len(intervalos)) if intervalos else None


# Rótulo/unidade de cada indicador do benchmark reprodutivo.
_BENCH_LABELS: dict[str, tuple[str, str]] = {
    "taxa_servico": ("Taxa de serviço", "%"),
    "taxa_concepcao": ("Taxa de concepção", "%"),
    "taxa_prenhez_ciclo": ("Taxa de prenhez", "%"),
    "del_medio": ("DEL médio", "dias"),
    "taxa_perda_prenhez": ("Taxa de perda de prenhez", "%"),
    "perc_vacas_prenhas": ("% de fêmeas prenhas", "%"),
    "servicos_por_prenhez": ("Serviços por prenhez", ""),
    "del_1a_ia": ("DEL médio à 1ª IA", "dias"),
    "dias_abertos": ("Dias abertos", "dias"),
    "iep_meses": ("Intervalo entre partos (IEP)", "meses"),
}


def _repro_benchmark(animais: list[dict], servicos: list[dict], partos: list[dict]) -> list[dict]:
    """Painel de benchmark reprodutivo (Prenhez = Serviço × Concepção) para um
    subconjunto do rebanho — usado para 'todas', 'vaca' e 'novilha'."""
    prenhes = vazias = inseminadas = 0
    for a in animais:
        sit = (a.get("sit_rep") or "").strip()
        if sit == "Ges.":
            prenhes += 1
        elif sit.startswith("Vaz."):
            vazias += 1
        elif sit == "Ins.":
            inseminadas += 1
    aptas = prenhes + vazias + inseminadas
    total = len(animais)

    serv_periodo = [s for s in servicos if _no_periodo(s)]
    pos = sum(1 for s in serv_periodo if _diag_upper(s.get("diagnostico")) == "POSITIVO")
    neg = sum(1 for s in serv_periodo if _diag_upper(s.get("diagnostico")) == "NEGATIVO")
    diag = pos + neg
    taxa_concepcao = round(100 * pos / diag, 1) if diag else None
    servidas = {s.get("numero_matriz") for s in serv_periodo if s.get("numero_matriz")}
    taxa_servico = round(100 * len(servidas) / aptas, 1) if aptas else None
    taxa_prenhez_ciclo = (
        round(taxa_servico * taxa_concepcao / 100, 1)
        if taxa_servico is not None and taxa_concepcao is not None else None
    )
    servicos_por_prenhez = round(len(serv_periodo) / pos, 1) if pos else None
    perdas = sum(1 for s in serv_periodo if s.get("data_perda_prenhez"))
    taxa_perda = round(100 * perdas / pos, 1) if pos else None
    perc_prenhas = round(100 * prenhes / total, 1) if total else None
    dias_abertos = _media([
        v for s in serv_periodo if _diag_upper(s.get("diagnostico")) == "POSITIVO"
        for v in [_del_serv(s)] if v is not None
    ])
    del_1a = _media([
        v for s in serv_periodo if s.get("ordem_tentativa") == 1
        for v in [_del_serv(s)] if v is not None
    ])
    del_medio = _media([
        float(a["del_dias"]) for a in animais
        if _codigo_grupo(a.get("grupo_primario")) in GRUPOS_LACTACAO and a.get("del_dias")
    ])
    iep_dias = _iep_dias(partos)
    iep_meses = round(iep_dias / 30.44, 1) if iep_dias else None

    valores = {
        "taxa_servico": taxa_servico, "taxa_concepcao": taxa_concepcao,
        "taxa_prenhez_ciclo": taxa_prenhez_ciclo, "del_medio": del_medio,
        "taxa_perda_prenhez": taxa_perda, "perc_vacas_prenhas": perc_prenhas,
        "servicos_por_prenhez": servicos_por_prenhez, "del_1a_ia": del_1a,
        "dias_abertos": dias_abertos, "iep_meses": iep_meses,
    }
    lista = []
    for chave, (label, unidade) in _BENCH_LABELS.items():
        m = BENCHMARK_METAS.get(chave, {})
        lista.append({
            "chave": chave, "label": label, "unidade": unidade,
            "valor": valores.get(chave), "meta": m.get("meta"),
            "media_pais": m.get("media_pais"), "maior_melhor": m.get("maior_melhor", True),
        })
    return lista


def _benchmark_categorias(animais: list[dict], servicos: list[dict], partos: list[dict]) -> dict:
    """Benchmark separado por categoria: todas / vaca (já pariu) / novilha."""
    vacas_nums = {p.get("numero_matriz") for p in partos if p.get("numero_matriz")}
    animais_vaca = [a for a in animais if a.get("numero") in vacas_nums]
    animais_novilha = [a for a in animais if a.get("numero") not in vacas_nums]
    serv_vaca = [s for s in servicos if (s.get("ordem_parto") or 0) >= 1]
    serv_novilha = [s for s in servicos if (s.get("ordem_parto") or 0) < 1]
    return {
        "todas": _repro_benchmark(animais, servicos, partos),
        "vaca": _repro_benchmark(animais_vaca, serv_vaca, partos),
        "novilha": _repro_benchmark(animais_novilha, serv_novilha, []),
    }


def calcular_indicadores(
    animais: list[dict],
    servicos: list[dict],
    partos: list[dict],
    data_ref: date | None = None,
) -> dict:
    """Calcula o painel de indicadores a partir dos dados carregados."""
    hoje = data_ref or date.today()

    # ---------------------------------------------------------------
    # Composição do rebanho
    # ---------------------------------------------------------------
    total = len(animais)
    distribuicao: dict[str, int] = {}
    for a in animais:
        g = a.get("grupo_primario") or "(sem grupo)"
        distribuicao[g] = distribuicao.get(g, 0) + 1

    codigos = [_codigo_grupo(a.get("grupo_primario")) for a in animais]
    vacas_lactacao = sum(1 for c in codigos if c in GRUPOS_LACTACAO)
    vacas_secas = sum(1 for c in codigos if c == GRUPO_SECAS)
    pre_parto = sum(1 for c in codigos if c == GRUPO_PRE_PARTO)

    # ---------------------------------------------------------------
    # Situação reprodutiva do rebanho apto
    # ---------------------------------------------------------------
    prenhes = vazias = inseminadas = 0
    for a in animais:
        sit = (a.get("sit_rep") or "").strip()
        if sit == "Ges.":
            prenhes += 1
        elif sit.startswith("Vaz."):
            vazias += 1
        elif sit == "Ins.":
            inseminadas += 1
    aptas = prenhes + vazias + inseminadas

    taxa_prenhez = round(100 * prenhes / aptas, 1) if aptas else None
    perc_vazias = round(100 * vazias / aptas, 1) if aptas else None

    # ---------------------------------------------------------------
    # Concepção — serviços diagnosticados (POSITIVO / NEGATIVO) desde 01/01/2026
    # ---------------------------------------------------------------
    pos = sum(1 for s in servicos if _no_periodo(s) and _diag_upper(s.get("diagnostico")) == "POSITIVO")
    neg = sum(1 for s in servicos if _no_periodo(s) and _diag_upper(s.get("diagnostico")) == "NEGATIVO")
    diagnosticados = pos + neg
    taxa_concepcao = round(100 * pos / diagnosticados, 1) if diagnosticados else None

    # ---------------------------------------------------------------
    # DEL e produção das lactantes
    # ---------------------------------------------------------------
    del_lactacao = [
        a.get("del_dias")
        for a in animais
        if _codigo_grupo(a.get("grupo_primario")) in GRUPOS_LACTACAO and a.get("del_dias")
    ]
    del_medio = _media([float(d) for d in del_lactacao])

    producoes = [
        a.get("ult_cl_kg")
        for a in animais
        if a.get("ult_cl_kg") and a.get("ult_cl_kg") > 0
    ]
    producao_media = _media([float(p) for p in producoes])
    producao_total_dia = round(sum(float(p) for p in producoes), 1) if producoes else 0.0

    # ---------------------------------------------------------------
    # IEP — intervalo entre partos (média, em dias e meses)
    # ---------------------------------------------------------------
    partos_por_matriz: dict[str, list[date]] = {}
    for p in partos:
        d = p.get("data_parto")
        m = p.get("numero_matriz")
        if d and m:
            partos_por_matriz.setdefault(m, []).append(d)

    intervalos: list[int] = []
    for datas in partos_por_matriz.values():
        # Colapsa registros do mesmo parto (mais próximos que o piso biológico),
        # ancorando sempre no parto distinto mais antigo, e mede o intervalo
        # apenas entre partos efetivamente distintos.
        distintos: list[date] = []
        for d in sorted(set(datas)):
            if not distintos or (d - distintos[-1]).days >= IEP_MINIMO_DIAS:
                distintos.append(d)
        for anterior, atual in zip(distintos, distintos[1:]):
            intervalos.append((atual - anterior).days)

    iep_dias = round(sum(intervalos) / len(intervalos)) if intervalos else None
    iep_meses = round(iep_dias / 30.44, 1) if iep_dias else None

    # ---------------------------------------------------------------
    # Partos previstos (prenhezes confirmadas → data provável de parto)
    # ---------------------------------------------------------------
    previstos = {"em_30_dias": 0, "em_60_dias": 0, "em_90_dias": 0}
    previstos_nums: dict[str, list[str]] = {"em_30_dias": [], "em_60_dias": [], "em_90_dias": []}
    for s in servicos:
        if _diag_upper(s.get("diagnostico")) != "POSITIVO":
            continue
        data_serv = s.get("data_servico")
        if not data_serv:
            continue
        parto = calcular_parto_provavel(data_serv, s.get("raca_matriz")).data_parto_provavel
        dias = (parto - hoje).days
        num = s.get("numero_matriz")
        if 0 <= dias <= 90:
            previstos["em_90_dias"] += 1
            if num:
                previstos_nums["em_90_dias"].append(num)
            if dias <= 60:
                previstos["em_60_dias"] += 1
                if num:
                    previstos_nums["em_60_dias"].append(num)
            if dias <= 30:
                previstos["em_30_dias"] += 1
                if num:
                    previstos_nums["em_30_dias"].append(num)

    # ---------------------------------------------------------------
    # Benchmark reprodutivo (eficiência) — desde CONCEPCAO_DESDE.
    # Modelo dos "medidores": Prenhez = Serviço × Concepção.
    # Calculado para todas / vaca (já pariu) / novilha.
    # ---------------------------------------------------------------
    benchmark_categorias = _benchmark_categorias(animais, servicos, partos)
    benchmark = benchmark_categorias["todas"]
    _bt = {b["chave"]: b["valor"] for b in benchmark}

    return {
        "data_referencia": hoje.isoformat(),
        "rebanho": {
            "total": total,
            "vacas_lactacao": vacas_lactacao,
            "vacas_secas": vacas_secas,
            "pre_parto": pre_parto,
            "distribuicao_grupos": dict(sorted(distribuicao.items())),
        },
        "reproducao": {
            "aptas": aptas,
            "prenhes": prenhes,
            "vazias": vazias,
            "inseminadas": inseminadas,
            "taxa_prenhez_pct": taxa_prenhez,
            "perc_vazias_pct": perc_vazias,
            "taxa_concepcao_pct": taxa_concepcao,
            "servicos_positivos": pos,
            "servicos_negativos": neg,
            "iep_dias": iep_dias,
            "iep_meses": iep_meses,
            "partos_previstos": previstos,
            "partos_previstos_nums": previstos_nums,
            "concepcao_desde": CONCEPCAO_DESDE.isoformat(),
            "taxa_servico_pct": _bt.get("taxa_servico"),
            "taxa_prenhez_ciclo_pct": _bt.get("taxa_prenhez_ciclo"),
            "servicos_por_prenhez": _bt.get("servicos_por_prenhez"),
            "taxa_perda_prenhez_pct": _bt.get("taxa_perda_prenhez"),
            "perc_vacas_prenhas_pct": _bt.get("perc_vacas_prenhas"),
            "dias_abertos": _bt.get("dias_abertos"),
            "del_1a_ia": _bt.get("del_1a_ia"),
        },
        "benchmark": benchmark,
        "benchmark_categorias": benchmark_categorias,
        "producao": {
            "vacas_com_producao": len(producoes),
            "producao_media_kg": producao_media,
            "producao_total_dia_kg": producao_total_dia,
            "del_medio": del_medio,
        },
    }
