"""
Testes do protótipo do Assistente Claude — cobrem o que dá para testar sem
uma chave real da API (gating admin, mensagem vazia, ferramentas isoladas e o
erro claro quando ANTHROPIC_API_KEY não está configurada). O laço de tool-use
em si (que de fato chama a Claude) não é coberto aqui — é comportamento da
API externa, não lógica nossa.
"""
from __future__ import annotations

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Animal
from fazenda.rules.assistente import _tool_buscar_animal, _tool_consultar_indicadores


@pytest.fixture
def client():
    import main
    from fazenda.auth import get_current_user

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    import fazenda.database as database
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with Session(engine) as s:
        s.add(Animal(numero="500", nome="Estrela", sexo="F", raca="Girolando"))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def test_rejeita_mensagem_vazia(client):
    c, engine = client
    r = c.post("/assistente/perguntar", json={"mensagem": "   "})
    assert r.status_code == 400


def test_sem_api_key_retorna_503(client, monkeypatch):
    c, engine = client
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_rejeita_nao_admin(client):
    c, engine = client
    import main
    from fazenda.auth import get_current_user

    class _FakeOperador:
        id = 2
        papel = "operador"
        ativo = True
        username = "op"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()
    r = c.post("/assistente/perguntar", json={"mensagem": "oi"})
    assert r.status_code == 403


class TestFerramentas:
    def test_consultar_indicadores(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_consultar_indicadores(s)
        assert "rebanho" in resultado
        assert "reproducao" in resultado

    def test_buscar_animal_encontrado(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_buscar_animal(s, "500")
        assert resultado["nome"] == "Estrela"

    def test_buscar_animal_inexistente(self, client):
        c, engine = client
        with Session(engine) as s:
            resultado = _tool_buscar_animal(s, "999")
        assert "erro" in resultado
