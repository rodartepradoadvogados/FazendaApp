"""
Alertas de estoque (saldo negativo / abaixo do mínimo) na Agenda — sempre
calculados (não dependem do opt-in "exibir necessidade de compra na agenda"
por item), visíveis só para quem tem acesso ao módulo de estoque.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Estoque


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


class _FakeOperadorSemEstoque:
    id = 2
    papel = "operador"
    permissoes = "agenda,sanidade"
    ativo = True
    username = "operador_sem_estoque"


class _FakeOperadorComEstoque:
    id = 3
    papel = "operador"
    permissoes = "agenda,estoque"
    ativo = True
    username = "operador_com_estoque"


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with Session(engine) as s:
        s.add(Estoque(nome="Terramicina", quantidade=-5.0, unidade="ml"))
        s.add(Estoque(nome="Ração Milho", quantidade=100.0, estoque_minimo=200.0, unidade="kg"))
        s.add(Estoque(nome="Sal Mineral", quantidade=300.0, estoque_minimo=200.0, unidade="kg"))
        s.add(Estoque(nome="Item Não Estocável", quantidade=-10.0, unidade="unidade", estocavel=False))
        s.commit()

    yield main.app
    main.app.dependency_overrides.clear()


def _client_as(app, user):
    from fazenda.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_admin_ve_negativo_e_abaixo_minimo(setup):
    c = _client_as(setup, _FakeAdmin())
    r = c.get("/agenda/")
    assert r.status_code == 200
    corpo = r.json()
    negativos = {i["nome"] for i in corpo["estoque_negativo"]}
    abaixo = {i["nome"] for i in corpo["estoque_abaixo_minimo"]}
    assert negativos == {"Terramicina"}
    assert abaixo == {"Ração Milho"}
    assert "Sal Mineral" not in abaixo  # 300 >= 200, dentro do normal
    assert "Item Não Estocável" not in negativos  # não participa de baixa/controle


def test_operador_sem_modulo_estoque_nao_ve_nada(setup):
    c = _client_as(setup, _FakeOperadorSemEstoque())
    r = c.get("/agenda/")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["estoque_negativo"] == []
    assert corpo["estoque_abaixo_minimo"] == []


def test_operador_com_modulo_estoque_ve_alertas(setup):
    c = _client_as(setup, _FakeOperadorComEstoque())
    r = c.get("/agenda/")
    assert r.status_code == 200
    corpo = r.json()
    assert {i["nome"] for i in corpo["estoque_negativo"]} == {"Terramicina"}
