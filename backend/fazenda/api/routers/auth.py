"""
Router de autenticação — login, dados do usuário logado e cadastro de usuários
(somente admin).
Endpoints: POST /auth/login · GET /auth/me · GET/POST /auth/usuarios
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from datetime import datetime

from fazenda.auth import EMAIL_DONO, MODULOS, criar_token, exigir_admin, exigir_dono, get_current_user, hash_senha, verificar_senha
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
    permissoes: list[str] = []
    email: str | None = None
    pode_publicar_materias_blog: bool = False


class EditarUsuario(BaseModel):
    username: str | None = None
    nome: str | None = None
    papel: str | None = None
    permissoes: list[str] | None = None
    ativo: bool | None = None
    senha: str | None = None
    email: str | None = None
    pode_publicar_materias_blog: bool | None = None


class PreferenciasIn(BaseModel):
    paleta: str | None = None
    email: str | None = None


def _publico(u: Usuario) -> dict:
    perms = MODULOS if u.papel == "admin" else [m for m in (u.permissoes or "").split(",") if m]
    return {"id": u.id, "username": u.username, "nome": u.nome, "papel": u.papel,
            "permissoes": perms, "ativo": u.ativo, "paleta": u.paleta or "vinho",
            "email": u.email, "eh_dono": (u.email or "").strip().lower() == EMAIL_DONO,
            "pode_publicar_materias_blog": u.pode_publicar_materias_blog}


@router.post("/login")
def login(dados: LoginIn, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(Usuario).where(Usuario.username == dados.username)).first()
    if not user or not user.ativo or not verificar_senha(dados.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    user.ultimo_login = datetime.utcnow()
    session.add(user)
    session.commit()
    return {"token": criar_token(user.username), "usuario": _publico(user)}


@router.get("/me")
def me(user: Usuario = Depends(get_current_user)) -> dict:
    return _publico(user)


@router.get("/usuarios")
def listar_usuarios(_: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> list[dict]:
    return [_publico(u) for u in session.exec(select(Usuario)).all()]


@router.get("/usuarios/acessos")
def listar_acessos(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    """Relatório de últimos acessos — restrito ao proprietário (ver exigir_dono)."""
    usuarios = session.exec(select(Usuario)).all()
    return [
        {"id": u.id, "username": u.username, "nome": u.nome, "papel": u.papel, "ativo": u.ativo,
         "ultimo_login": u.ultimo_login.isoformat() if u.ultimo_login else None}
        for u in sorted(usuarios, key=lambda u: (u.ultimo_login is None, u.ultimo_login or datetime.min), reverse=True)
    ]


@router.get("/modulos")
def listar_modulos(_: Usuario = Depends(get_current_user)) -> list[str]:
    return MODULOS


@router.post("/usuarios")
def criar_usuario(dados: NovoUsuario, _: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> dict:
    if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")
    perms = "" if dados.papel == "admin" else ",".join(m for m in dados.permissoes if m in MODULOS)
    novo = Usuario(username=dados.username, nome=dados.nome, senha_hash=hash_senha(dados.senha),
                   papel=dados.papel, permissoes=perms, email=(dados.email or "").strip() or None,
                   pode_publicar_materias_blog=dados.pode_publicar_materias_blog)
    session.add(novo)
    session.commit()
    session.refresh(novo)
    return _publico(novo)


@router.put("/usuarios/{user_id}")
def editar_usuario(user_id: int, dados: EditarUsuario, admin: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> dict:
    u = session.get(Usuario, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if dados.username is not None and dados.username != u.username:
        if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
            raise HTTPException(status_code=400, detail="Já existe um usuário com esse login")
        u.username = dados.username
    if dados.nome is not None:
        u.nome = dados.nome
    if dados.papel is not None:
        u.papel = dados.papel
    if dados.permissoes is not None:
        u.permissoes = "" if (dados.papel or u.papel) == "admin" else ",".join(m for m in dados.permissoes if m in MODULOS)
    if dados.ativo is not None:
        # não deixa o admin desativar a si mesmo
        if u.id == admin.id and not dados.ativo:
            raise HTTPException(status_code=400, detail="Não é possível desativar você mesmo")
        u.ativo = dados.ativo
    if dados.senha:
        u.senha_hash = hash_senha(dados.senha)
    if dados.email is not None:
        u.email = dados.email.strip() or None
    if dados.pode_publicar_materias_blog is not None:
        u.pode_publicar_materias_blog = dados.pode_publicar_materias_blog
    session.add(u)
    session.commit()
    session.refresh(u)
    return _publico(u)


@router.put("/preferencias")
def salvar_preferencias(dados: PreferenciasIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    """Preferências pessoais (paleta, e-mail) — cada usuário edita as suas, sem precisar ser admin."""
    if dados.paleta is not None:
        if dados.paleta not in ("vinho", "verde"):
            raise HTTPException(status_code=400, detail="Paleta inválida")
        user.paleta = dados.paleta
    if dados.email is not None:
        user.email = dados.email.strip() or None
    session.add(user)
    session.commit()
    session.refresh(user)
    return _publico(user)
