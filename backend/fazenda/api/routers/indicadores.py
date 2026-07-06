"""
Router de indicadores — painel zootécnico/reprodutivo/produtivo do rebanho.
Endpoint: GET /indicadores/
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, Parto, Servico
from fazenda.rules.indicadores import calcular_indicadores

router = APIRouter(prefix="/indicadores", tags=["indicadores"])


@router.get("/")
def obter_indicadores(
    data: date = date.today(),
    session: Session = Depends(get_session),
) -> dict:
    """
    Indicadores consolidados do rebanho: composição, situação reprodutiva
    (taxa de prenhez, concepção, IEP, partos previstos) e produção (DEL médio,
    litros/dia). Calculado sobre os dados já carregados via upload.
    """
    animais = [a.model_dump() for a in session.exec(select(Animal).where(Animal.ativo == True)).all()]
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    partos = [p.model_dump() for p in session.exec(select(Parto)).all()]

    return calcular_indicadores(animais, servicos, partos, data_ref=data)
