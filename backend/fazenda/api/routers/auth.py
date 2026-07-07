"""
Router de autenticação — login, dados do usuário logado e cadastro de usuários
(somente admin).
Endpoints: POST /auth/login · GET /auth/me · GET/POST /auth/usuarios
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import criar_token, exigir_admin, get_current_user, hash_senha, verificar_senha
from fazenda.database import get_session
from fazenda.models import Usuario

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    senha: str


class NovoUsuario(BaseModel):
    username: str
    senha: str
    nome: str | None = None
    papel: str = "operador"


def _publico(u: Usuario) -> dict:
    return {"id": u.id, "username": u.username, "nome": u.nome, "papel": u.papel, "ativo": u.ativo}


@router.post("/login")
def login(dados: LoginIn, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(Usuario).where(Usuario.username == dados.username)).first()
    if not user or not user.ativo or not verificar_senha(dados.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    return {"token": criar_token(user.username), "usuario": _publico(user)}


@router.get("/me")
def me(user: Usuario = Depends(get_current_user)) -> dict:
    return _publico(user)


@router.get("/usuarios")
def listar_usuarios(_: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> list[dict]:
    return [_publico(u) for u in session.exec(select(Usuario)).all()]


@router.post("/usuarios")
def criar_usuario(dados: NovoUsuario, _: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> dict:
    if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")
    novo = Usuario(username=dados.username, nome=dados.nome, senha_hash=hash_senha(dados.senha), papel=dados.papel)
    session.add(novo)
    session.commit()
    session.refresh(novo)
    return _publico(novo)
