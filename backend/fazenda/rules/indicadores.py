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

# Códigos de grupo (2 primeiros dígitos do grupo_primario).
GRUPOS_LACTACAO = {"01", "02", "03"}
GRUPO_PRE_PARTO = "04"
GRUPO_SECAS = "05"


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
    # Concepção — serviços diagnosticados (POSITIVO / NEGATIVO)
    # ---------------------------------------------------------------
    pos = sum(1 for s in servicos if _diag_upper(s.get("diagnostico")) == "POSITIVO")
    neg = sum(1 for s in servicos if _diag_upper(s.get("diagnostico")) == "NEGATIVO")
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
        datas_ord = sorted(datas)
        for anterior, atual in zip(datas_ord, datas_ord[1:]):
            intervalos.append((atual - anterior).days)

    iep_dias = round(sum(intervalos) / len(intervalos)) if intervalos else None
    iep_meses = round(iep_dias / 30.44, 1) if iep_dias else None

    # ---------------------------------------------------------------
    # Partos previstos (prenhezes confirmadas → data provável de parto)
    # ---------------------------------------------------------------
    previstos = {"em_30_dias": 0, "em_60_dias": 0, "em_90_dias": 0}
    for s in servicos:
        if _diag_upper(s.get("diagnostico")) != "POSITIVO":
            continue
        data_serv = s.get("data_servico")
        if not data_serv:
            continue
        parto = calcular_parto_provavel(data_serv, s.get("raca_matriz")).data_parto_provavel
        dias = (parto - hoje).days
        if 0 <= dias <= 90:
            previstos["em_90_dias"] += 1
            if dias <= 60:
                previstos["em_60_dias"] += 1
            if dias <= 30:
                previstos["em_30_dias"] += 1

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
        },
        "producao": {
            "vacas_com_producao": len(producoes),
            "producao_media_kg": producao_media,
            "producao_total_dia_kg": producao_total_dia,
            "del_medio": del_medio,
        },
    }
