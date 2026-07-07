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
from fazenda.models import Usuario

SECRET = os.environ.get("AUTH_SECRET", "fazenda-estreito-ponte-de-pedra-troque-em-producao")
PBKDF2_ITER = 120_000
TOKEN_VALIDADE_S = 60 * 60 * 12  # 12 horas


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


def exigir_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.papel != "admin":
        raise HTTPException(status_code=403, detail="Requer administrador")
    return user


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
