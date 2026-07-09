"""
Testes de lançamento de sanidade: múltiplos produtos por aplicação e
compatibilidade de unidade com a baixa de estoque.
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
            s.add(Estoque(nome="Borgal 50ml", quantidade=1000, unidade="ml"))
            s.add(Estoque(nome="Vacina X", quantidade=20, unidade="unidade"))
            s.add(Estoque(nome="Serviço veterinário", quantidade=0, unidade="unidade", estocavel=False))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestUnidadesCompativeis:
    def test_ml_aceita_ml_unidade_dose_nao_litro(self, client):
        r = client.get("/sanidade/unidades-compativeis", params={"produto": "Borgal 50ml"})
        assert set(r.json()) == {"ml", "unidade", "dose"}
        assert "L" not in r.json()

    def test_produto_sem_estoque_libera_tudo(self, client):
        r = client.get("/sanidade/unidades-compativeis", params={"produto": "Não cadastrado"})
        assert "ml" in r.json() and "L" in r.json()


class TestRegistrarAplicacao:
    def test_multiplos_produtos_um_animal(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [
                {"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"},
                {"produto": "Vacina X", "quantidade": 1, "unidade": "unidade"},
            ],
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 2

    def test_um_produto_varios_animais_do_lote(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101", "102", "103"],
            "itens": [{"produto": "Vacina X", "quantidade": 1, "unidade": "unidade"}],
        })
        assert r.json()["criados"] == 3

    def test_unidade_compativel_da_baixa_direta(self, client):
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101", "102"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        r = client.get("/estoque/")
        item = next(i for i in r.json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 980  # 1000 - 10*2

    def test_unidade_incompativel_da_400(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 1, "unidade": "L"}],
        })
        assert r.status_code == 400

    def test_unidade_compativel_mas_diferente_da_estoque_avisa_sem_baixar(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 1, "unidade": "unidade"}],
        })
        assert r.status_code == 200
        assert len(r.json()["avisos"]) == 1
        estoque = client.get("/estoque/").json()["itens"]
        item = next(i for i in estoque if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 1000  # não deu baixa

    def test_sem_animais_da_400(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": [],
            "itens": [{"produto": "Vacina X", "quantidade": 1, "unidade": "unidade"}],
        })
        assert r.status_code == 400

    def test_sem_itens_da_400(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"], "itens": [],
        })
        assert r.status_code == 400

    def test_item_nao_estocavel_nao_da_baixa(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Serviço veterinário", "quantidade": 1, "unidade": "unidade"}],
        })
        assert r.status_code == 200
        assert r.json()["avisos"] == []
        estoque = client.get("/estoque/").json()["itens"]
        item = next(i for i in estoque if i["nome"] == "Serviço veterinário")
        assert item["quantidade"] == 0

    def test_baixa_direta_gera_movimento_de_estoque(self, client):
        # Antes, a baixa direta mexia em Estoque.quantidade sem deixar rastro
        # em MovimentoEstoque — ficava invisível no histórico/RMCA físico.
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101", "102"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        r = client.get("/estoque/movimentos")
        movimentos = [m for m in r.json()["movimentos"] if m["nome_item"] == "Borgal 50ml"]
        assert len(movimentos) == 1
        assert movimentos[0]["movimento"] == "Aplicação"
        assert movimentos[0]["quantidade"] == 20  # 10ml * 2 animais
