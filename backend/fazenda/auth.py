"""
Autenticação — sem dependências externas (stdlib apenas).

- Senhas: PBKDF2-HMAC-SHA256 com salt aleatório (formato pbkdf2$iter$salt$hash).
- Token: payload base64url assinado com HMAC-SHA256 (parecido com JWT), com
  validade (exp). O segredo vem de AUTH_SECRET (env) — defina em produção.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import SeedFlag, Usuario

SECRET = os.environ.get("AUTH_SECRET", "fazenda-estreito-ponte-de-pedra-troque-em-producao")
PBKDF2_ITER = 120_000
TOKEN_VALIDADE_S = 60 * 60 * 12  # 12 horas

# E-mail do proprietário — único com acesso ao relatório de últimos acessos
# (ver /auth/usuarios/acessos). Fixo por enquanto, sem UI de gestão.
EMAIL_DONO = "rodartepradoadvogados@gmail.com"


# ---------------------------------------------------------------------------
# Senha
# ---------------------------------------------------------------------------
def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), PBKDF2_ITER)
    return f"pbkdf2${PBKDF2_ITER}${salt}${dk.hex()}"


def verificar_senha(senha: str, guardado: str) -> bool:
    try:
        _, iters, salt, h = guardado.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def criar_token(username: str) -> str:
    payload = _b64(json.dumps({"sub": username, "exp": int(time.time()) + TOKEN_VALIDADE_S}).encode())
    sig = _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def validar_token(token: str) -> str | None:
    try:
        payload, sig = token.split(".")
        esperado = _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, esperado):
            return None
        dados = json.loads(_unb64(payload))
        if dados.get("exp", 0) < time.time():
            return None
        return dados.get("sub")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dependências FastAPI
# ---------------------------------------------------------------------------
def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Usuario:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    username = validar_token(authorization.split(" ", 1)[1])
    if not username:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")
    user = session.exec(select(Usuario).where(Usuario.username == username)).first()
    if not user or not user.ativo:
        raise HTTPException(status_code=401, detail="Usuário inativo")
    return user


def get_current_user_opcional(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Usuario | None:
    """Igual a get_current_user, mas retorna None em vez de 401 sem token —
    para rotas públicas (ex.: leitura do blog News) que também aceitam login."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    username = validar_token(authorization.split(" ", 1)[1])
    if not username:
        return None
    user = session.exec(select(Usuario).where(Usuario.username == username)).first()
    if not user or not user.ativo:
        return None
    return user


def exigir_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.papel != "admin":
        raise HTTPException(status_code=403, detail="Requer administrador")
    return user


def exigir_dono(user: Usuario = Depends(get_current_user)) -> Usuario:
    """Restringe a UM único usuário — o proprietário — por e-mail cadastrado.
    Independente de papel/admin: mesmo outro admin não passa por aqui."""
    if (user.email or "").strip().lower() != EMAIL_DONO:
        raise HTTPException(status_code=403, detail="Acesso restrito ao proprietário")
    return user


def exigir_pode_publicar(user: Usuario = Depends(get_current_user)) -> Usuario:
    """Permissão específica para publicar/gerenciar matérias do blog (News) e
    confirmar a revisão de publicação definitiva. Independente de papel/admin
    — igual exigir_dono, um admin comum não passa por aqui sem a flag."""
    if not user.pode_publicar_materias_blog:
        raise HTTPException(status_code=403, detail="Sem permissão para publicar matérias no blog")
    return user


# Módulos do sistema (chaves usadas nas permissões dos operadores).
MODULOS = [
    "capa", "indicadores", "agenda", "lancamentos", "reproducao", "analise",
    "rebanho", "producao", "alimentacao", "sanidade", "financeiro", "estoque",
    "pedidos", "parametros", "upload",
]


def tem_modulo(user: Usuario, modulo: str) -> bool:
    if user.papel == "admin":
        return True
    liberados = {m.strip() for m in (user.permissoes or "").split(",") if m.strip()}
    return modulo in liberados


def exigir_modulo(modulo: str):
    """Dependência: exige que o usuário logado tenha acesso ao módulo."""
    def _dep(user: Usuario = Depends(get_current_user)) -> Usuario:
        if not tem_modulo(user, modulo):
            raise HTTPException(status_code=403, detail=f"Sem acesso ao módulo '{modulo}'")
        return user
    return _dep


def exigir_modulo_qualquer(*modulos: str):
    """Dependência: exige acesso a QUALQUER UM dos módulos — para dados lidos
    por mais de uma área do site (ex.: banco de touros, usado tanto em
    Configurações > Cadastro quanto em Rebanho > Touros)."""
    def _dep(user: Usuario = Depends(get_current_user)) -> Usuario:
        if not any(tem_modulo(user, m) for m in modulos):
            raise HTTPException(status_code=403, detail=f"Sem acesso a nenhum dos módulos: {', '.join(modulos)}")
        return user
    return _dep


# ---------------------------------------------------------------------------
# Seed do administrador inicial
# ---------------------------------------------------------------------------
def seed_admin(session: Session) -> None:
    """Cria o admin inicial se ainda não houver nenhum usuário."""
    existe = session.exec(select(Usuario)).first()
    if existe:
        return
    username = os.environ.get("ADMIN_USER", "AlexandreRodarte")
    senha = os.environ.get("ADMIN_PASS", "820908")
    session.add(Usuario(username=username, nome="Alexandre Rodarte", senha_hash=hash_senha(senha), papel="admin"))
    session.commit()


def seed_permissao_publicar_dono(session: Session) -> None:
    """Uma única vez (SeedFlag): o proprietário (EMAIL_DONO) já nasce com a
    permissão de publicar matérias no blog, já que ele já usa essa função hoje
    (Configurações > News > Adicionar matéria ao blog). Todos os demais
    usuários — inclusive outros admins — começam sem essa permissão, como
    pedido; essa migração nunca roda de novo DEPOIS de aplicada, então o
    proprietário pode revogar a própria depois se quiser.

    Só marca a SeedFlag quando o usuário do dono já existe — o admin inicial
    (seed_admin) nasce sem e-mail, então se o e-mail só for cadastrado depois
    (Configurações > Usuários), esta migração tenta de novo no próximo
    startup em vez de desistir silenciosamente e deixar o botão "Confirmar
    revisão definitiva" sempre desabilitado."""
    chave = "pode_publicar_materias_blog_dono_202607"
    if session.get(SeedFlag, chave):
        return
    dono = session.exec(select(Usuario).where(Usuario.email == EMAIL_DONO)).first()
    if not dono:
        return
    dono.pode_publicar_materias_blog = True
    session.add(dono)
    session.add(SeedFlag(chave=chave))
    session.commit()
