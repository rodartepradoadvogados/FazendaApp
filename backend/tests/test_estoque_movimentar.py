"""
Testes de lançamento de entrada/saída de estoque — dá baixa ou soma direto
na quantidade do item.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Estoque


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        with Session(engine) as s:
            s.add(Estoque(nome="Borgal 50ml", quantidade=10, estoque_minimo=5, unidade="unidade"))
            s.add(Estoque(nome="Frete de touro", quantidade=0, unidade="unidade", estocavel=False))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestMovimentarEstoque:
    def test_saida_da_baixa(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Aplicação", "quantidade": 3,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 200
        assert r.json()["quantidade"] == 7

    def test_entrada_soma(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Entrada de ajuste", "quantidade": 5,
            "data_movimento": "2026-07-08",
        })
        assert r.json()["quantidade"] == 15

    def test_marca_abaixo_minimo(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Saída de ajuste", "quantidade": 8,
            "data_movimento": "2026-07-08",
        })
        assert r.json()["quantidade"] == 2
        assert r.json()["abaixo_minimo"] is True

    def test_item_inexistente_da_404(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Não existe", "movimento": "Aplicação", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 404

    def test_movimento_invalido_da_400(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Sei lá", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 400

    def test_registra_historico(self, client):
        client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Aplicação", "quantidade": 3,
            "data_movimento": "2026-07-08", "observacao": "teste",
        })
        r = client.get("/estoque/movimentos")
        assert r.json()["total"] == 1
        assert r.json()["movimentos"][0]["nome_item"] == "Borgal 50ml"


class TestCriarItemEstoque:
    def test_cria_item_com_campos_completos(self, client):
        r = client.post("/estoque/", json={
            "nome": "Sal mineral", "categoria": "Alimento", "unidade": "saca 30kg",
            "quantidade": 10, "estoque_minimo": 5, "valor_unitario": 80.0,
            "carencia_dias": 0, "centro_custo_padrao": "Pecuária",
            "conta_gerencial_despesa_padrao": "3.01.01.03",
            "exibir_necessidade_compra_agenda": True,
        })
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["nome"] == "Sal mineral"
        assert corpo["valor_total"] == 800.0
        assert corpo["ativo"] is True
        assert corpo["exibir_necessidade_compra_agenda"] is True
        assert corpo["conta_gerencial_despesa_padrao"] == "3.01.01.03"

    def test_nome_duplicado_da_409(self, client):
        r = client.post("/estoque/", json={"nome": "Borgal 50ml"})
        assert r.status_code == 409

    def test_marca_abaixo_minimo_na_criacao(self, client):
        r = client.post("/estoque/", json={"nome": "Concentrado", "quantidade": 2, "estoque_minimo": 10})
        assert r.json()["abaixo_minimo"] is True

    def test_estocavel_default_true(self, client):
        r = client.post("/estoque/", json={"nome": "Concentrado2", "quantidade": 2})
        assert r.json()["estocavel"] is True

    def test_cria_item_nao_estocavel(self, client):
        r = client.post("/estoque/", json={"nome": "Serviço de frete", "estocavel": False})
        assert r.json()["estocavel"] is False


class TestEstocavel:
    def test_doacao_rejeitada_para_item_nao_estocavel(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Frete de touro", "movimento": "Doação", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 400

    def test_entrada_cortesia_rejeitada_para_item_nao_estocavel(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Frete de touro", "movimento": "Entrada de cortesia", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 400

    def test_ajuste_normal_permitido_para_item_nao_estocavel(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Frete de touro", "movimento": "Entrada de ajuste", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 200

    def test_doacao_permitida_para_item_estocavel(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Doação", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 200
