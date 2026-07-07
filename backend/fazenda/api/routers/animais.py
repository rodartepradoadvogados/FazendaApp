"""
Router de animais — listagem e consulta de animais.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal

router = APIRouter(prefix="/animais", tags=["animais"])


@router.get("/")
def listar_animais(
    grupo: str | None = Query(None, description="Filtrar por grupo primário"),
    sit_rep: str | None = Query(None, description="Filtrar por situação reprodutiva"),
    ativo: bool = Query(True),
    incluir_machos: bool = Query(False, description="Incluir machos e sêmen (padrão: só fêmeas)"),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(Animal).where(Animal.ativo == ativo)
    if grupo:
        query = query.where(Animal.grupo_primario.contains(grupo))
    if sit_rep:
        query = query.where(Animal.sit_rep == sit_rep)

    animais = session.exec(query).all()
    if not incluir_machos:
        # Rebanho = só fêmeas. Exclui sêmen/reprodutores e machos. Registros
        # antigos (sem o campo) permanecem até o próximo upload do GERAL.
        animais = [a for a in animais if not a.eh_semen and a.sexo != "M"]
    return [a.model_dump() for a in animais]


@router.get("/{numero}")
def buscar_animal(numero: str, session: Session = Depends(get_session)) -> dict:
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Animal {numero} não encontrado")
    return animal.model_dump()
