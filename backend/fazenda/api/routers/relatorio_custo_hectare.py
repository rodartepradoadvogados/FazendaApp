"""
Custo por hectare — indicador Financeiro > Relatórios (arquivo próprio para
não mexer em `financeiro.py`). Reaproveita o mesmo prefixo `/financeiro`
(FastAPI permite vários routers com o mesmo prefixo — ver `main.py`).

Segue o mesmo espírito do indicador "Custo por litro de leite"
(`GET /financeiro/custo-litro-leite`), mas em vez de dividir o custo de
alimentação pelos litros entregues, divide as despesas do período (mesmo
filtro de competência/centro de custo do DRE, ver `GET /financeiro/dre`)
pela área total da fazenda em hectares — parâmetro `area_total_hectares`
(Configurações > Parâmetros > Estrutura da fazenda, ver
`fazenda.rules.parametros`).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import ContaGerencial
from fazenda.rules.custo_hectare import calcular_custo_por_hectare
from fazenda.rules.parametros import area_total_hectares

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


@router.get("/custo-hectare")
def custo_por_hectare(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    centro_custo: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict:
    """
    Custo por hectare — despesas do período (ContaGerencial por competência,
    com filtro opcional de centro de custo) dividido pela área total da
    fazenda em hectares (Configurações > Parâmetros).
    """
    contas = session.exec(select(ContaGerencial)).all()
    filtradas = [
        c for c in contas
        if c.data_competencia and data_inicio <= c.data_competencia <= data_fim
        and (centro_custo is None or c.centro_custo == centro_custo)
    ]
    despesas_total = sum(c.valor_total or 0 for c in filtradas if c.tipo == "despesa")
    area = area_total_hectares()

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "centro_custo": centro_custo,
        "area_configurada": bool(area and area > 0),
        **calcular_custo_por_hectare(despesas_total, area),
    }
