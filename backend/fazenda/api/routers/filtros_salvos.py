"""
Router de Filtros salvos — cada usuário pode nomear e reaplicar com um clique
o conjunto de filtros de uma tela de relatório (ex.: Financeiro > Extrato
completo). Ver fazenda/models/filtro_salvo.py.

Genérico por design: qualquer tela pode adotar, bastando escolher uma chave
de `tela` própria (ex.: "financeiro_extrato") e mandar/receber um dict livre
de filtros — o backend não conhece o formato de nenhuma tela específica.

Registrado em main.py com _protegido (só _contrato_ativo é opcional aqui,
já que salvar um filtro não deveria ficar bloqueado por módulo contratado
— é uma preferência pessoal do usuário, não uma funcionalidade de negócio).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import FiltroSalvo, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/filtros-salvos", tags=["filtros-salvos"])


def _serializar(f: FiltroSalvo) -> dict:
    try:
        filtros = json.loads(f.filtros)
    except (TypeError, ValueError):
        filtros = {}
    return {"id": f.id, "tela": f.tela, "nome": f.nome, "filtros": filtros, "criado_em": f.criado_em.isoformat()}


@router.get("")
def listar_filtros_salvos(
    tela: str,
    user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
) -> list[dict]:
    filtros = session.exec(
        select(FiltroSalvo)
        .where(FiltroSalvo.usuario_id == user.id, FiltroSalvo.tela == tela)
        .order_by(FiltroSalvo.criado_em)
    ).all()
    return [_serializar(f) for f in filtros]


class FiltroSalvoIn(BaseModel):
    tela: str
    nome: str
    filtros: dict


@router.post("", status_code=201)
def criar_filtro_salvo(
    dados: FiltroSalvoIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if not dados.tela.strip():
        raise HTTPException(400, "Tela obrigatória")
    if not dados.nome.strip():
        raise HTTPException(400, "Nome obrigatório")

    filtro = FiltroSalvo(
        usuario_id=user.id,
        fazenda_id=fazenda_id_seguro(fazenda_id),
        tela=dados.tela.strip(),
        nome=dados.nome.strip(),
        filtros=json.dumps(dados.filtros),
    )
    session.add(filtro)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(400, f'Já existe um filtro salvo chamado "{dados.nome.strip()}" nesta tela')
    session.refresh(filtro)
    return _serializar(filtro)


@router.delete("/{filtro_id}")
def excluir_filtro_salvo(
    filtro_id: int, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
) -> dict:
    filtro = session.get(FiltroSalvo, filtro_id)
    if not filtro or filtro.usuario_id != user.id:
        raise HTTPException(404, "Filtro salvo não encontrado")
    session.delete(filtro)
    session.commit()
    return {"excluido": True}
