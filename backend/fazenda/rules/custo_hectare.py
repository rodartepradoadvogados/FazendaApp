"""
Custo por hectare — indicador Financeiro > Relatórios. Divide o total de
despesas do período (ContaGerencial, filtradas por competência e,
opcionalmente, por centro de custo) pela área total da fazenda em hectares
(Configurações > Parâmetros > Estrutura da fazenda, chave
`area_total_hectares`) — mesmo espírito do indicador de Custo por litro de
leite (ver `custo_leite.py`), mas usando área em vez de litros como
denominador.
"""
from __future__ import annotations


def calcular_custo_por_hectare(despesas_total: float, area_hectares: float | None) -> dict:
    return {
        "area_hectares": round(area_hectares, 2) if area_hectares else None,
        "despesas_total": round(despesas_total, 2),
        "custo_por_hectare": round(despesas_total / area_hectares, 2) if area_hectares else None,
    }
