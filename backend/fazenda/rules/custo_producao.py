"""
Custo por vaca e por lote — indicador Financeiro > Relatórios. Mesmo espírito
de `custo_leite.py`/`custo_hectare.py`: soma um total de despesas do período e
divide por uma contagem — aqui, o número de vacas em lactação no período
(uma vaca só entra na conta se tiver ao menos um Controle leiteiro lançado
no período, o que a identifica como efetivamente em produção). O rateio por
lote é proporcional ao número de vacas de cada lote sobre o total — não há
hoje nenhum vínculo direto entre lançamento financeiro e lote/animal, então
não é possível saber quanto de cada despesa "pertence" a um lote específico.
"""
from __future__ import annotations


def calcular_custo_por_vaca(despesas_total: float, num_vacas: int) -> dict:
    return {
        "num_vacas": num_vacas,
        "despesas_total": round(despesas_total, 2),
        "custo_por_vaca": round(despesas_total / num_vacas, 2) if num_vacas else None,
    }


def calcular_custo_por_lote(despesas_total: float, vacas_por_lote: dict[str, int]) -> list[dict]:
    """Rateia `despesas_total` entre os lotes, proporcional ao número de
    vacas de cada um sobre o total. Lotes sem nenhuma vaca no período não
    aparecem no resultado."""
    total_vacas = sum(vacas_por_lote.values())
    if not total_vacas:
        return []
    linhas = []
    for lote, num_vacas in sorted(vacas_por_lote.items()):
        if num_vacas <= 0:
            continue
        custo_alocado = despesas_total * num_vacas / total_vacas
        linhas.append({
            "lote": lote,
            "num_vacas": num_vacas,
            "custo_alocado": round(custo_alocado, 2),
            "custo_por_vaca": round(custo_alocado / num_vacas, 2),
        })
    return linhas
