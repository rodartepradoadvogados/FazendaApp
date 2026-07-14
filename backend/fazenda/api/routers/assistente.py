"""
Router do Assistente Claude (protótipo) — POST /assistente/perguntar.
Disponível para qualquer usuário logado; cada ferramenta interna é oferecida
só a quem tem o módulo correspondente liberado (ver fazenda.rules.assistente).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import Usuario
from fazenda.rules.assistente import responder

router = APIRouter(prefix="/assistente", tags=["assistente"])


class PerguntaIn(BaseModel):
    mensagem: str
    historico: list[dict] = []


@router.post("/perguntar")
def perguntar(
    dados: PerguntaIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(get_current_user),
) -> dict:
    if not dados.mensagem.strip():
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    try:
        return responder(dados.mensagem.strip(), dados.historico, session, usuario)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
