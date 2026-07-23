"""
Piloto conservador de multi-fazenda — cadastro de Fazenda e vínculo com
Usuario. Restrito ao proprietário (mesma trava de /auth/usuarios) enquanto
isto for só um piloto interno: criar uma fazenda ou vincular alguém a ela é
uma operação sensível (decide quem vê o quê), não um cadastro comum.

Ver fazenda/models/multitenant.py (Fazenda/UsuarioFazenda) e
fazenda/api/routers/auth.py (POST /auth/login, POST /auth/selecionar-fazenda).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_dono, get_current_user
from fazenda.database import get_session
from fazenda.models import Fazenda, Usuario, UsuarioFazenda

router = APIRouter(prefix="/fazendas", tags=["fazendas"])


def _publico(f: Fazenda) -> dict:
    return {"id": f.id, "nome": f.nome, "cidade": f.cidade, "uf": f.uf, "ativa": f.ativa}


class FazendaIn(BaseModel):
    nome: str
    cidade: str | None = None
    uf: str | None = None


class VincularUsuarioIn(BaseModel):
    usuario_id: int


@router.get("/")
def listar_fazendas(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    return [_publico(f) for f in session.exec(select(Fazenda)).all()]


@router.get("/minhas")
def minhas_fazendas(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    """Fazendas vinculadas ao usuário logado — usado pela tela de "trocar de
    fazenda" (o login já devolve a mesma lista quando há mais de uma)."""
    vinculos = session.exec(select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == user.id)).all()
    fazendas = [session.get(Fazenda, v.fazenda_id) for v in vinculos]
    return [_publico(f) for f in fazendas if f and f.ativa]


@router.post("/")
def criar_fazenda(dados: FazendaIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome da fazenda é obrigatório")
    fazenda = Fazenda(nome=nome, cidade=(dados.cidade or "").strip() or None, uf=(dados.uf or "").strip() or None)
    session.add(fazenda)
    session.commit()
    session.refresh(fazenda)
    return _publico(fazenda)


@router.post("/{fazenda_id}/vincular-usuario")
def vincular_usuario(
    fazenda_id: int, dados: VincularUsuarioIn, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    fazenda = session.get(Fazenda, fazenda_id)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    usuario = session.get(Usuario, dados.usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    ja_vinculado = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario.id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()
    if ja_vinculado:
        raise HTTPException(status_code=400, detail=f"{usuario.username} já está vinculado a esta fazenda")
    session.add(UsuarioFazenda(usuario_id=usuario.id, fazenda_id=fazenda_id))
    session.commit()
    return {"vinculado": True}


@router.delete("/{fazenda_id}/vincular-usuario/{usuario_id}")
def desvincular_usuario(
    fazenda_id: int, usuario_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)
) -> dict:
    vinculo = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario_id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()
    if not vinculo:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    session.delete(vinculo)
    session.commit()
    return {"desvinculado": True}
