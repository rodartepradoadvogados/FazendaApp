"""
Testes de POST/PUT /auth/usuarios — toda conta de login exige uma Pessoa já
cadastrada (nunca nome livre) e cada pessoa só pode estar vinculada a um
único usuário por vez (ver fazenda.api.routers.auth._validar_pessoa_do_usuario).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import hash_senha
from fazenda.models import Pessoa, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="admin", nome="Admin", senha_hash=hash_senha("123"), papel="admin"))
        s.add(Pessoa(nome="João Silva", tipo="Funcionário"))
        s.add(Pessoa(nome="Maria Souza", tipo="Funcionário"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _login(c, username="admin"):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def _pessoa_id(engine, nome):
    with Session(engine) as s:
        return s.exec(select(Pessoa).where(Pessoa.nome == nome)).first().id


def test_criar_usuario_exige_pessoa_existente(client):
    c, engine = client
    token = _login(c)
    r = c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": 9999, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_criar_usuario_deriva_nome_da_pessoa(client):
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "João Silva")
    r = c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": pid, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    dados = r.json()
    assert dados["nome"] == "João Silva"
    assert dados["pessoa_id"] == pid
    assert dados["pessoa_nome"] == "João Silva"


def test_criar_usuario_rejeita_pessoa_ja_vinculada(client):
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "João Silva")
    r1 = c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": pid, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    r2 = c.post(
        "/auth/usuarios",
        json={"username": "joao2", "senha": "123", "pessoa_id": pid, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 400
    assert "joao" in r2.json()["detail"]


def test_editar_usuario_associa_pessoa_retroativamente(client):
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "Maria Souza")

    with Session(engine) as s:
        antigo = Usuario(username="legado", nome="Legado", senha_hash=hash_senha("123"), papel="operador")
        s.add(antigo)
        s.commit()
        s.refresh(antigo)
        legado_id = antigo.id

    r = c.put(
        f"/auth/usuarios/{legado_id}",
        json={"pessoa_id": pid},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    dados = r.json()
    assert dados["pessoa_id"] == pid
    assert dados["nome"] == "Maria Souza"


def test_editar_usuario_rejeita_pessoa_ja_vinculada_a_outro(client):
    c, engine = client
    token = _login(c)
    pid_joao = _pessoa_id(engine, "João Silva")
    pid_maria = _pessoa_id(engine, "Maria Souza")

    c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": pid_joao, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    r_maria = c.post(
        "/auth/usuarios",
        json={"username": "maria", "senha": "123", "pessoa_id": pid_maria, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    maria_id = r_maria.json()["id"]

    r = c.put(
        f"/auth/usuarios/{maria_id}",
        json={"pessoa_id": pid_joao},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_editar_usuario_permite_manter_mesma_pessoa(client):
    c, engine = client
    token = _login(c)
    pid = _pessoa_id(engine, "João Silva")
    r_criado = c.post(
        "/auth/usuarios",
        json={"username": "joao", "senha": "123", "pessoa_id": pid, "papel": "operador", "permissoes": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    user_id = r_criado.json()["id"]

    r = c.put(
        f"/auth/usuarios/{user_id}",
        json={"pessoa_id": pid, "email": "joao@x.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "joao@x.com"
