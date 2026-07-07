"""
Router de parâmetros — metas e configurações zootécnicas de referência.
Endpoint: GET /parametros/
"""
from __future__ import annotations

from fastapi import APIRouter

from fazenda.rules.parametros import PARAMETROS

router = APIRouter(prefix="/parametros", tags=["parametros"])


@router.get("/")
def obter_parametros() -> dict:
    """Parâmetros de manejo e metas usados como referência nos indicadores."""
    return {"grupos": PARAMETROS}
