"""
Router de reprodução — dados achatados para o dashboard interativo de análise.
Endpoint: GET /reproducao/servicos
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Servico
from fazenda.rules.reproducao_analise import analisar_servicos

router = APIRouter(prefix="/reproducao", tags=["reproducao"])


@router.get("/servicos")
def listar_servicos_analise(session: Session = Depends(get_session)) -> dict:
    """
    Todos os serviços achatados com as dimensões da análise reprodutiva
    (concepção/perda por categoria, raça, ordem de parto/tentativa, condição
    de IA, inseminador, mês, DEL). O front filtra/agrega no cliente.
    """
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    registros = analisar_servicos(servicos)
    return {"servicos": registros, "total": len(registros)}
