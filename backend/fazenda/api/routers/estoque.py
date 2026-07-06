"""
Router de estoque — inventário completo de insumos.
Endpoint: GET /estoque/
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Estoque

router = APIRouter(prefix="/estoque", tags=["estoque"])


@router.get("/")
def listar_estoque(session: Session = Depends(get_session)) -> dict:
    """Todos os itens de estoque para o dashboard interativo (filtra no cliente)."""
    itens = [e.model_dump() for e in session.exec(select(Estoque)).all()]
    return {"itens": itens, "total": len(itens)}
