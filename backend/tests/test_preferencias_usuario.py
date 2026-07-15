"""
Testes de PUT /auth/preferencias — preferência pessoal de paleta de cores
(Vinho/Verde), que qualquer usuário logado edita para si mesmo (sem precisar
ser admin).
"""
from __future__ import annotations

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="operador-teste", nome="Operador", senha_hash="x", papel="operador", permissoes=""))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    def _current_user_override(session: Session = Depends(database.get_session)):
        return session.exec(select(Usuario).where(Usuario.username == "operador-teste")).first()

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = _current_user_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def test_paleta_padrao_e_vinho(client):
    c, _ = client
    r = c.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["paleta"] == "vinho"


def test_salvar_e_persistir_paleta_verde(client):
    c, engine = client
    r = c.put("/auth/preferencias", json={"paleta": "verde"})
    assert r.status_code == 200
    assert r.json()["paleta"] == "verde"

    with Session(engine) as s:
        u = s.exec(select(Usuario).where(Usuario.username == "operador-teste")).first()
        assert u.paleta == "verde"

    # Persiste entre chamadas — /auth/me reflete o valor salvo.
    r = c.get("/auth/me")
    assert r.json()["paleta"] == "verde"


def test_paleta_invalida_rejeitada(client):
    c, _ = client
    r = c.put("/auth/preferencias", json={"paleta": "azul"})
    assert r.status_code == 400
