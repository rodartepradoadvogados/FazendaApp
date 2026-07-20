"""
Custo por vaca e por lote — indicador Financeiro > Relatórios (arquivo
próprio para não mexer em financeiro.py). Reaproveita o prefixo /financeiro
(FastAPI permite vários routers com o mesmo prefixo — ver main.py).

Segue o mesmo espírito do "Custo por litro de leite" (GET
/financeiro/custo-litro-leite): soma despesas do período (ContaGerencial,
por competência e centro de custo) e divide por uma contagem de produção —
aqui, o número de vacas em lactação (identificadas por terem ao menos um
Controle leiteiro no período). O rateio por lote é proporcional ao número
de vacas de cada lote sobre o total (ver fazenda.rules.custo_producao).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, ContaGerencial, ControleLeiteiro
from fazenda.rules.custo_producao import calcular_custo_por_lote, calcular_custo_por_vaca

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

CENTRO_CUSTO_PADRAO = "Pecuária Leiteira"


def _despesas_periodo(session: Session, data_inicio: date, data_fim: date, centro_custo: str | None) -> float:
    contas = session.exec(select(ContaGerencial)).all()
    return round(sum(
        c.valor_total or 0 for c in contas
        if c.tipo == "despesa" and c.data_competencia and data_inicio <= c.data_competencia <= data_fim
        and (centro_custo is None or c.centro_custo == centro_custo)
    ), 2)


def _vacas_por_lote_no_periodo(session: Session, data_inicio: date, data_fim: date) -> dict[str, int]:
    """Vacas com ao menos um Controle leiteiro no período — identifica quem
    esteve efetivamente em lactação/produção, agrupadas pelo lote atual do
    animal (Animal.grupo_primario)."""
    numeros = {
        c.numero_matriz for c in session.exec(select(ControleLeiteiro)).all()
        if c.data_controle and data_inicio <= c.data_controle <= data_fim
    }
    if not numeros:
        return {}
    vacas_por_lote: dict[str, int] = {}
    for a in session.exec(select(Animal)).all():
        if a.numero in numeros:
            lote = a.grupo_primario or "Sem lote"
            vacas_por_lote[lote] = vacas_por_lote.get(lote, 0) + 1
    return vacas_por_lote


@router.get("/custo-vaca-lote")
def custo_por_vaca_e_lote(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    centro_custo: str | None = Query(CENTRO_CUSTO_PADRAO),
    session: Session = Depends(get_session),
) -> dict:
    despesas_total = _despesas_periodo(session, data_inicio, data_fim, centro_custo)
    vacas_por_lote = _vacas_por_lote_no_periodo(session, data_inicio, data_fim)
    total_vacas = sum(vacas_por_lote.values())

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "centro_custo": centro_custo,
        "tem_vacas_no_periodo": bool(total_vacas),
        "por_lote": calcular_custo_por_lote(despesas_total, vacas_por_lote),
        **calcular_custo_por_vaca(despesas_total, total_vacas),
    }
