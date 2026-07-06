"""
Router de produção — indicadores do histórico de controle leiteiro.
Endpoint: GET /producao/
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import ControleLeiteiro
from fazenda.rules.producao import calcular_producao

router = APIRouter(prefix="/producao", tags=["producao"])


@router.get("/")
def obter_producao(session: Session = Depends(get_session)) -> dict:
    """Série temporal, curva de lactação e ranking por vaca do controle leiteiro."""
    controles = [c.model_dump() for c in session.exec(select(ControleLeiteiro)).all()]
    return calcular_producao(controles)


@router.get("/controles")
def listar_controles(session: Session = Depends(get_session)) -> dict:
    """Registros de controle leiteiro achatados para o dashboard interativo."""
    registros = []
    for c in session.exec(select(ControleLeiteiro)).all():
        d = c.data_controle
        registros.append({
            "numero": c.numero_matriz,
            "raca": c.raca or "(sem raça)",
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "producao_kg": c.producao_kg,
            "del": c.del_no_controle,
        })
    return {"controles": registros, "total": len(registros)}
