"""
Router de sanidade — histórico de medicamentos aplicados nos animais.
Endpoint: GET /sanidade/aplicacoes
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Sanidade

router = APIRouter(prefix="/sanidade", tags=["sanidade"])


@router.get("/aplicacoes")
def listar_aplicacoes(session: Session = Depends(get_session)) -> dict:
    """Aplicações achatadas para o dashboard interativo (filtra no cliente)."""
    registros = []
    for s in session.exec(select(Sanidade)).all():
        d = s.data_aplicacao
        registros.append({
            "numero": s.numero_matriz,
            "raca": s.raca or "(sem raça)",
            "produto": s.produto,
            "categoria": s.categoria or "Outros",
            "dose": s.dose,
            "atividade": s.atividade,
            "obs": s.obs,
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "mes": f"{d.year}-{d.month:02d}" if d else None,
        })
    return {"aplicacoes": registros, "total": len(registros)}
