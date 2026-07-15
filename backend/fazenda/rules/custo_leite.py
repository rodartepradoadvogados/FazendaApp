"""
Custo por litro de leite — indicador Financeiro > Relatórios. Divide o custo
de alimentação do período (mesmas contas gerenciais marcadas para o RMCA,
rmca_custo_alimentacao) pelos litros de leite entregues no período (Entrega
mensal do leite), projetados proporcionalmente por dia quando o período não
bate exatamente com o mês fechado da entrega — mesmo critério de projeção já
usado em Produção > Controle × Entregue.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta


def _dias_por_mes_no_periodo(ini: date, fim: date) -> dict[tuple[int, int], int]:
    out: dict[tuple[int, int], int] = {}
    d = ini
    while d <= fim:
        chave = (d.year, d.month)
        out[chave] = out.get(chave, 0) + 1
        d += timedelta(days=1)
    return out


def litros_leite_no_periodo(entregas_por_competencia: dict[str, float], ini: date, fim: date) -> float:
    total = 0.0
    for (ano, mes), dias_no_mes_periodo in _dias_por_mes_no_periodo(ini, fim).items():
        comp = f"{ano:04d}-{mes:02d}"
        if comp not in entregas_por_competencia:
            continue
        dias_do_mes = calendar.monthrange(ano, mes)[1]
        total += entregas_por_competencia[comp] / dias_do_mes * dias_no_mes_periodo
    return total


def calcular_custo_por_litro(custo_total: float, litros: float) -> dict:
    return {
        "litros": round(litros, 1),
        "custo_total": round(custo_total, 2),
        "custo_por_litro": round(custo_total / litros, 4) if litros else None,
    }
