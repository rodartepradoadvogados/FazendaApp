"""
Custo por hectare e por tonelada de uma Safra — Opção A do plano de custo
agrícola (ver fazenda.api.routers.relatorio_custo_safra). Mesmo espírito de
rules/custo_hectare.py, só que dividindo pelo hectare/tonelada cadastrados na
própria safra em vez da área total da fazenda.
"""
from __future__ import annotations


def calcular_custo_safra(despesas_total: float, hectares: float | None, toneladas: float | None) -> dict:
    return {
        "despesas_total": round(despesas_total, 2),
        "hectares": round(hectares, 2) if hectares else None,
        "toneladas_produzidas": round(toneladas, 2) if toneladas else None,
        "custo_por_hectare": round(despesas_total / hectares, 2) if hectares else None,
        "custo_por_tonelada": round(despesas_total / toneladas, 2) if toneladas else None,
    }
