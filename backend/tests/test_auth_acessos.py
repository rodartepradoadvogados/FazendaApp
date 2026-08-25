"""
Testes de:
- login registra ultimo_login;
- GET /auth/usuarios/acessos (relatório de últimos acessos) — dono-equivalente
  OU administrador (papel == "admin"), ver fazenda.auth.exigir_admin_ou_dono
  (ampliado de exigir_dono puro a pedido explícito do usuário, ago/2026).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.add(Usuario(username="outro-admin", nome="Outro", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com"))
        s.add(Usuario(username="operador", nome="Operador", senha_hash=hash_senha("123"), papel="operador"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _login(c, username):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_login_registra_ultimo_login(client):
    c, engine = client
    with Session(engine) as s:
        u = s.exec(select(Usuario).where(Usuario.username == "dono")).first()
        assert u.ultimo_login is None
    _login(c, "dono")
    with Session(engine) as s:
        u = s.exec(select(Usuario).where(Usuario.username == "dono")).first()
        assert u.ultimo_login is not None


def test_acessos_liberado_para_dono(client):
    c, _ = client
    token = _login(c, "dono")
    r = c.get("/auth/usuarios/acessos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    usernames = {u["username"] for u in r.json()}
    assert usernames == {"dono", "outro-admin", "operador"}


def test_acessos_liberado_para_outro_admin(client):
    """Qualquer `papel == "admin"` agora passa (exigir_admin_ou_dono) — antes
    só quem estivesse em EMAILS_DONO_EQUIVALENTE."""
    c, _ = client
    token = _login(c, "outro-admin")
    r = c.get("/auth/usuarios/acessos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_acessos_bloqueado_para_operador(client):
    c, _ = client
    token = _login(c, "operador")
    r = c.get("/auth/usuarios/acessos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_publico_expoe_eh_dono(client):
    c, _ = client
    token_dono = _login(c, "dono")
    r = c.get("/auth/me", headers={"Authorization": f"Bearer {token_dono}"})
    assert r.json()["eh_dono"] is True

    token_outro = _login(c, "outro-admin")
    r = c.get("/auth/me", headers={"Authorization": f"Bearer {token_outro}"})
    assert r.json()["eh_dono"] is False
