"""
Router de produção — indicadores do histórico de controle leiteiro e
lançamento de pesagens (por vaca ou por lote inteiro, de uma vez).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, ControleLeiteiro
from fazenda.rules.producao import calcular_producao

router = APIRouter(prefix="/producao", tags=["producao"])


class OrdenhaIn(BaseModel):
    numero_matriz: str
    ordenhas: list[float]


class ControlesIn(BaseModel):
    data_controle: date
    entradas: list[OrdenhaIn]


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


@router.post("/controles")
def criar_controles(dados: ControlesIn, session: Session = Depends(get_session)) -> dict:
    """
    Registra a pesagem do dia para uma ou várias vacas de uma vez (lançamento
    individual ou em lote — o front manda uma entrada por vaca do lote).
    """
    criados = []
    for entrada in dados.entradas:
        if not entrada.ordenhas or not any(entrada.ordenhas):
            continue
        animal = session.exec(select(Animal).where(Animal.numero == entrada.numero_matriz)).first()
        registro = ControleLeiteiro(
            animal_id=animal.id if animal else None,
            numero_matriz=entrada.numero_matriz,
            raca=animal.raca if animal else None,
            data_controle=dados.data_controle,
            producao_kg=round(sum(entrada.ordenhas), 2),
            del_no_controle=animal.del_dias if animal else None,
        )
        session.add(registro)
        criados.append(registro)
    session.commit()
    return {"criados": len(criados)}
