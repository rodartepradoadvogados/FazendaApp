"""
Router de relatórios gerenciais e de manejo reprodutivo.

Endpoints:
- GET /relatorios/manejo — 8 listas semaforizadas (o que fazer hoje).
- GET /relatorios/gerencial/distribuicao-del?ordem&del_min&del_max
- GET /relatorios/gerencial/prenhezes-por-del?del_min&del_max
- GET /relatorios/gerencial/dias-diagnostico?del_min&del_max
- GET /relatorios/gerencial/intervalo-servicos
- GET /relatorios/gerencial/dias-reinseminacao
- GET /relatorios/gerencial/taxa-servico-prenhez
- GET /relatorios/gerencial/fluxo-lactacao?meses
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, EstoqueSemen, Parto, Servico
from fazenda.rules import relatorios_gerenciais as rg

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


def _dados(session: Session):
    animais = [a.model_dump() for a in session.exec(select(Animal)).all()]
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    partos = [p.model_dump() for p in session.exec(select(Parto)).all()]
    return animais, servicos, partos


@router.get("/manejo")
def relatorios_manejo(session: Session = Depends(get_session)) -> dict:
    animais, servicos, partos = _dados(session)
    semen = [s.model_dump() for s in session.exec(select(EstoqueSemen)).all()]
    return rg.relatorios_manejo(animais, servicos, partos, semen, date.today())


@router.get("/gerencial/distribuicao-del")
def gerencial_distribuicao_del(
    ordem: int = Query(1, ge=1, le=4, description="1, 2, 3 ou 4 (=4º ou mais)"),
    del_min: int = Query(0, ge=0),
    del_max: int = Query(350, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    _, servicos, _ = _dados(session)
    return rg.distribuicao_del(servicos, ordem, del_min, del_max)


@router.get("/gerencial/prenhezes-por-del")
def gerencial_prenhezes_por_del(
    del_min: int = Query(0, ge=0),
    del_max: int = Query(400, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    _, servicos, _ = _dados(session)
    return rg.prenhezes_por_del(servicos, del_min, del_max)


@router.get("/gerencial/dias-diagnostico")
def gerencial_dias_diagnostico(
    del_min: int = Query(0, ge=0),
    del_max: int = Query(400, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    _, servicos, _ = _dados(session)
    return rg.dias_para_diagnostico(servicos, del_min, del_max)


@router.get("/gerencial/intervalo-servicos")
def gerencial_intervalo_servicos(session: Session = Depends(get_session)) -> dict:
    _, servicos, _ = _dados(session)
    return rg.intervalo_entre_servicos(servicos)


@router.get("/gerencial/dias-reinseminacao")
def gerencial_dias_reinseminacao(session: Session = Depends(get_session)) -> dict:
    _, servicos, partos = _dados(session)
    return rg.dias_para_reinseminacao(servicos, partos)


@router.get("/gerencial/taxa-servico-prenhez")
def gerencial_taxa_servico_prenhez(session: Session = Depends(get_session)) -> dict:
    animais, servicos, partos = _dados(session)
    return rg.taxa_servico_prenhez(animais, servicos, partos, date.today())


@router.get("/gerencial/fluxo-lactacao")
def gerencial_fluxo_lactacao(
    meses: int = Query(8, ge=1, le=24),
    session: Session = Depends(get_session),
) -> dict:
    animais, servicos, partos = _dados(session)
    return rg.fluxo_lactacao(animais, servicos, partos, date.today(), meses)
