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

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import ContaGerencial
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.centro_custo import valor_gerencial_por_centro_custo
from fazenda.rules.custo_hectare import calcular_custo_por_hectare
from fazenda.rules.parametros import area_total_hectares
from fazenda.rules.vale_item import ajuste_vale_por_conta

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


@router.get("/custo-hectare")
def custo_por_hectare(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    centro_custo: str | None = Query(None),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    """
    Custo por hectare — despesas do período (ContaGerencial por competência,
    com filtro opcional de centro de custo) dividido pela área total da
    fazenda em hectares (Configurações > Parâmetros).
    """
    # Escopado na fazenda autenticada. Antes somava a ContaGerencial de TODAS
    # as fazendas (o custo/hectare do cliente saía com a despesa dos outros
    # clientes dentro) — ver tests/test_isolamento_relatorios_fornecedor.py (G2).
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ContaGerencial)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query).all()
    periodo = [c for c in contas if c.data_competencia and data_inicio <= c.data_competencia <= data_fim]
    # Vale de funcionário/empreiteiro lançado a partir de um item não é
    # despesa da fazenda — ver rules/vale_item.py.
    ajustes = ajuste_vale_por_conta(session, periodo, None)
    # Item com centro de custo próprio (override) é rateado entre os centros
    # dos itens em vez de cair inteiro no centro de custo da nota — ver
    # valor_gerencial_por_centro_custo.
    valores = valor_gerencial_por_centro_custo(session, periodo, centro_custo, ajustes)
    filtradas = periodo if centro_custo is None else [c for c in periodo if valores.get(c.id, 0.0) != 0]
    despesas_total = sum(valores.get(c.id, 0.0) for c in filtradas if c.tipo == "despesa")
    area = area_total_hectares()

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "centro_custo": centro_custo,
        "area_configurada": bool(area and area > 0),
        **calcular_custo_por_hectare(despesas_total, area),
    }
