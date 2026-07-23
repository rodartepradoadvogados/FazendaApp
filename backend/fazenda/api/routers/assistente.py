"""
Router do Assistente Claude (protótipo) — POST /assistente/perguntar.
Disponível para qualquer usuário logado da fazenda #1 (a única em uso hoje);
cada ferramenta interna é oferecida só a quem tem o módulo correspondente
liberado (ver fazenda.rules.assistente).

Piloto de multi-fazenda (ver fazenda/models/multitenant.py): por decisão do
dono, o assistente NÃO entra no pacote padrão de uma fazenda nova por
enquanto — fica restrito à fazenda já existente. `fazenda_id` só é None para
token emitido antes do piloto (comportamento idêntico ao de hoje).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Usuario
from fazenda.rules.assistente import responder

router = APIRouter(prefix="/assistente", tags=["assistente"])

FAZENDA_ID_PILOTO = 1


class PerguntaIn(BaseModel):
    mensagem: str
    historico: list[dict] = []


@router.post("/perguntar")
def perguntar(
    dados: PerguntaIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if fazenda_id is not None and fazenda_id != FAZENDA_ID_PILOTO:
        raise HTTPException(status_code=403, detail="Assistente ainda não disponível para esta fazenda")
    if not dados.mensagem.strip():
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    try:
        return responder(dados.mensagem.strip(), dados.historico, session, usuario)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
