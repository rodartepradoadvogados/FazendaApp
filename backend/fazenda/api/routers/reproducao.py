"""
Router de reprodução — dados achatados para o dashboard interativo de análise
e lançamento de diagnóstico de gestação.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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


class DiagnosticoIn(BaseModel):
    numero_matriz: str
    data_diagnostico: date
    resultado: str  # "retoque" | "reconfirmada" | "negativo"
    metodo: str | None = None


@router.post("/diagnostico")
def registrar_diagnostico(dados: DiagnosticoIn, session: Session = Depends(get_session)) -> dict:
    """
    Registra o resultado do diagnóstico de gestação no serviço mais recente da
    matriz. Se marcado "retoque", o lembrete de reconfirmação entra na agenda
    na data do próximo serviço (agenda_engine.py).
    """
    if dados.resultado not in ("retoque", "reconfirmada", "negativo"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    servico = session.exec(
        select(Servico)
        .where(Servico.numero_matriz == dados.numero_matriz)
        .order_by(Servico.data_servico.desc())
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_diagnostico = dados.data_diagnostico
    if dados.resultado == "retoque":
        servico.diagnostico = "POSITIVO"
        servico.retoque = True
    elif dados.resultado == "reconfirmada":
        servico.diagnostico = "POSITIVO"
        servico.retoque = False
    else:
        servico.diagnostico = "NEGATIVO"
        servico.retoque = False

    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()
