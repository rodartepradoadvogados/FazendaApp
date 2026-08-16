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

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Animal, ContaGerencial, ControleLeiteiro
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.centro_custo import valor_gerencial_por_centro_custo
from fazenda.rules.custo_producao import calcular_custo_por_lote, calcular_custo_por_vaca
from fazenda.rules.vale_item import ajuste_vale_por_conta

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

CENTRO_CUSTO_PADRAO = "Pecuária Leiteira"


def _despesas_periodo(
    session: Session, data_inicio: date, data_fim: date, centro_custo: str | None, fazenda_id: int | None = None,
) -> float:
    query = select(ContaGerencial)
    if fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query).all()
    periodo = [c for c in contas if c.tipo == "despesa" and c.data_competencia and data_inicio <= c.data_competencia <= data_fim]
    # Vale de funcionário/empreiteiro lançado a partir de um item não é
    # despesa da fazenda — ver rules/vale_item.py.
    ajustes = ajuste_vale_por_conta(session, periodo, fazenda_id)
    # Item com centro de custo próprio (override) é rateado entre os centros
    # dos itens em vez de cair inteiro no centro de custo da nota — ver
    # valor_gerencial_por_centro_custo.
    valores = valor_gerencial_por_centro_custo(session, periodo, centro_custo, ajustes)
    filtradas = periodo if centro_custo is None else [c for c in periodo if valores.get(c.id, 0.0) != 0]
    return round(sum(valores.get(c.id, 0.0) for c in filtradas), 2)


def _vacas_por_lote_no_periodo(
    session: Session, data_inicio: date, data_fim: date, fazenda_id: int | None = None,
) -> dict[str, int]:
    """Vacas com ao menos um Controle leiteiro no período — identifica quem
    esteve efetivamente em lactação/produção, agrupadas pelo lote atual do
    animal (Animal.grupo_primario)."""
    controle_query = select(ControleLeiteiro)
    animal_query = select(Animal)
    if fazenda_id is not None:
        controle_query = controle_query.where(ControleLeiteiro.fazenda_id == fazenda_id)
        animal_query = animal_query.where(Animal.fazenda_id == fazenda_id)
    numeros = {
        c.numero_matriz for c in session.exec(controle_query).all()
        if c.data_controle and data_inicio <= c.data_controle <= data_fim
    }
    if not numeros:
        return {}
    vacas_por_lote: dict[str, int] = {}
    for a in session.exec(animal_query).all():
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    despesas_total = _despesas_periodo(session, data_inicio, data_fim, centro_custo, fazenda_id=fazenda_id)
    vacas_por_lote = _vacas_por_lote_no_periodo(session, data_inicio, data_fim, fazenda_id=fazenda_id)
    total_vacas = sum(vacas_por_lote.values())

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "centro_custo": centro_custo,
        "tem_vacas_no_periodo": bool(total_vacas),
        "por_lote": calcular_custo_por_lote(despesas_total, vacas_por_lote),
        **calcular_custo_por_vaca(despesas_total, total_vacas),
    }
