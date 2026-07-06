"""
Produção — indicadores a partir do histórico de controle leiteiro.

Entrega:
  - serie_temporal: por data de controle → nº vacas, produção total e média (kg)
  - curva_lactacao: produção média por faixa de DEL (0-30, 31-60, ...)
  - por_animal: resumo por vaca (nº controles, última produção, média, pico)
"""
from __future__ import annotations

from collections import defaultdict

# Faixas de DEL (dias em lactação) para a curva.
_FAIXAS = [(0, 30), (31, 60), (61, 90), (91, 120), (121, 150), (151, 200), (201, 300), (301, 9999)]


def _rotulo_faixa(inicio: int, fim: int) -> str:
    return f"{inicio}-{fim}" if fim < 9999 else f"{inicio}+"


def _media(vals: list[float]) -> float:
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def calcular_producao(controles: list[dict]) -> dict:
    validos = [c for c in controles if c.get("producao_kg") is not None and c.get("data_controle")]

    # Série temporal por data
    por_data: dict = defaultdict(list)
    for c in validos:
        por_data[c["data_controle"]].append(float(c["producao_kg"]))
    serie_temporal = [
        {
            "data": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "vacas": len(vals),
            "total_kg": round(sum(vals), 1),
            "media_kg": _media(vals),
        }
        for d, vals in sorted(por_data.items())
    ]

    # Curva de lactação por faixa de DEL
    por_faixa: dict = defaultdict(list)
    for c in validos:
        del_c = c.get("del_no_controle")
        if del_c is None or del_c < 0:
            continue
        for inicio, fim in _FAIXAS:
            if inicio <= del_c <= fim:
                por_faixa[(inicio, fim)].append(float(c["producao_kg"]))
                break
    curva_lactacao = [
        {
            "faixa_del": _rotulo_faixa(inicio, fim),
            "controles": len(por_faixa[(inicio, fim)]),
            "media_kg": _media(por_faixa[(inicio, fim)]),
        }
        for (inicio, fim) in _FAIXAS
        if por_faixa.get((inicio, fim))
    ]

    # Resumo por animal
    por_matriz: dict = defaultdict(list)
    for c in validos:
        por_matriz[c["numero_matriz"]].append(c)
    por_animal = []
    for numero, regs in por_matriz.items():
        regs_ord = sorted(regs, key=lambda r: r["data_controle"])
        vals = [float(r["producao_kg"]) for r in regs_ord]
        por_animal.append({
            "numero_matriz": numero,
            "controles": len(regs_ord),
            "ultima_kg": vals[-1],
            "media_kg": _media(vals),
            "pico_kg": max(vals),
        })
    por_animal.sort(key=lambda x: -x["media_kg"])

    return {
        "totais": {
            "vacas": len(por_matriz),
            "controles": len(validos),
            "ultima_media_kg": serie_temporal[-1]["media_kg"] if serie_temporal else None,
            "ultima_data": serie_temporal[-1]["data"] if serie_temporal else None,
        },
        "serie_temporal": serie_temporal,
        "curva_lactacao": curva_lactacao,
        "por_animal": por_animal,
    }
