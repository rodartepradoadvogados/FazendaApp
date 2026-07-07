"""
Router de animais — listagem e consulta de animais.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, Parto, Servico

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

    # Datas reprodutivas por matriz: último serviço POSITIVO (concepção) e último
    # parto. Usadas no front para dias de gestação, dias para o parto e PEV.
    ult_pos: dict[str, object] = {}
    for s in session.exec(select(Servico)).all():
        d = s.data_servico
        if d and (s.diagnostico or "").strip().upper() == "POSITIVO":
            if s.numero_matriz not in ult_pos or d > ult_pos[s.numero_matriz]:
                ult_pos[s.numero_matriz] = d
    ult_parto: dict[str, object] = {}
    for p in session.exec(select(Parto)).all():
        d = p.data_parto
        if d and (p.numero_matriz not in ult_parto or d > ult_parto[p.numero_matriz]):
            ult_parto[p.numero_matriz] = d

    saida = []
    for a in animais:
        d = a.model_dump()
        sp = ult_pos.get(a.numero)
        pp = ult_parto.get(a.numero)
        d["data_ult_servico_pos"] = sp.isoformat() if sp else None
        d["data_ult_parto"] = pp.isoformat() if pp else None
        saida.append(d)
    return saida


@router.get("/{numero}")
def buscar_animal(numero: str, session: Session = Depends(get_session)) -> dict:
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Animal {numero} não encontrado")
    return animal.model_dump()
