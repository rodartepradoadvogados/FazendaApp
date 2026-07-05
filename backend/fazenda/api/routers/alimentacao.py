"""
Router de alimentação — plano de dieta por lote e consumo diário estimado.
Endpoint: GET /alimentacao/
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, Dieta
from fazenda.rules.alimentacao import calcular_consumo

router = APIRouter(prefix="/alimentacao", tags=["alimentacao"])


@router.get("/")
def obter_alimentacao(session: Session = Depends(get_session)) -> dict:
    """Plano de dieta por lote cruzado com o efetivo atual → consumo/dia por ingrediente."""
    dietas = [d.model_dump() for d in session.exec(select(Dieta)).all()]
    animais = [a.model_dump() for a in session.exec(select(Animal).where(Animal.ativo == True)).all()]
    return calcular_consumo(dietas, animais)
