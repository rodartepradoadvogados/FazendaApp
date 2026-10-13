"""
Plano Financeiro, fase 1.4 — `contrato_status` no objeto fazenda de
/auth/login e /auth/me (contrato de API, item E). Ida-e-volta: o dono
PUT/aprova/suspende o contrato e o que o CLIENTE recebe muda junto com
`modulos_contratados`.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Fazenda, Usuario, UsuarioFazenda


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=2, nome="Fazenda Financeira"))
        s.add(Fazenda(id=3, nome="Fazenda Sem Contrato"))
        s.add(Usuario(id=1, username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.add(Usuario(id=2, username="cliente", nome="Cliente", senha_hash=hash_senha("123"), papel="admin", email="c@x.com"))
        s.add(Usuario(id=3, username="cliente3", nome="Cliente 3", senha_hash=hash_senha("123"), papel="admin", email="c3@x.com"))
        s.commit()
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=2))
        s.add(UsuarioFazenda(usuario_id=3, fazenda_id=3))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _login(c, username):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200, r.text
    return r.json()


def _fazenda_do_cliente(c, username="cliente"):
    """O que o cliente vê no login E no /auth/me — têm de concordar."""
    dados = _login(c, username)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {dados['token']}"})
    assert me.status_code == 200, me.text
    return dados["fazenda_atual"], me.json()["fazenda_atual"]


def test_contrato_status_acompanha_put_aprovar_e_suspender(client):
    c = client
    dono = {"Authorization": f"Bearer {_login(c, 'dono')['token']}"}

    # Fazenda sem contrato nenhum: status null, módulos vazios.
    no_login, no_me = _fazenda_do_cliente(c, "cliente3")
    assert no_login["contrato_status"] is None and no_me["contrato_status"] is None
    assert no_login["modulos_contratados"] == []

    # Contrato definido mas não aprovado.
    r = c.put("/fazendas/2/contrato", json={"plano": "financeiro", "modulos": []}, headers=dono)
    assert r.status_code == 200, r.text
    no_login, no_me = _fazenda_do_cliente(c)
    for f in (no_login, no_me):
        assert f["contrato_status"] == "aguardando_aprovacao"
        assert f["modulos_contratados"] == ["financeiro", "pedidos"]

    # Aprovado.
    assert c.post("/fazendas/2/contrato/aprovar", headers=dono).status_code == 200
    no_login, no_me = _fazenda_do_cliente(c)
    assert no_login["contrato_status"] == no_me["contrato_status"] == "ativo"

    # Troca de módulos (sob medida) reflete junto, sem trocar o status.
    c.put("/fazendas/2/contrato", headers=dono, json={
        "plano": None, "modulos": [{"modulo": "rebanho", "preco": 10.0}, {"modulo": "financeiro", "preco": 10.0}],
    })
    no_login, no_me = _fazenda_do_cliente(c)
    assert no_login["modulos_contratados"] == no_me["modulos_contratados"] == ["financeiro", "rebanho"]
    assert no_me["contrato_status"] == "ativo"

    # Suspenso.
    assert c.post("/fazendas/2/contrato/suspender", headers=dono).status_code == 200
    no_login, no_me = _fazenda_do_cliente(c)
    assert no_login["contrato_status"] == no_me["contrato_status"] == "suspenso"
