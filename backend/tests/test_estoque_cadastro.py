"""
Testes de cadastro de item de estoque — POST /estoque/ (criação) e
PUT /estoque/{id} (edição completa, usada pelo botão "editar" da tabela
filtrada de Estoque no site), incluindo o campo tipo_semen (sexado/convencional).
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
        yield c, engine

    main.app.dependency_overrides.clear()


class TestCriarItemEstoque:
    def test_cria_item_com_tipo_semen(self, client):
        c, _ = client
        r = c.post("/estoque/", json={
            "nome": "Sêmen 7HO12345", "categoria": "Sêmen e genética",
            "unidade": "dose", "quantidade": 10, "tipo_semen": "sexado",
        })
        assert r.status_code == 201, r.text
        assert r.json()["tipo_semen"] == "sexado"

    def test_nao_duplica_nome(self, client):
        c, _ = client
        c.post("/estoque/", json={"nome": "Ração X", "unidade": "kg"})
        r = c.post("/estoque/", json={"nome": "Ração X", "unidade": "kg"})
        assert r.status_code == 409

    def test_flag_gera_patrimonio(self, client):
        c, _ = client
        r = c.post("/estoque/", json={"nome": "Trator Massey", "gera_patrimonio": True})
        assert r.status_code == 201, r.text
        assert r.json()["gera_patrimonio"] is True

    def test_gera_patrimonio_padrao_false(self, client):
        c, _ = client
        r = c.post("/estoque/", json={"nome": "Ração Y", "unidade": "kg"})
        assert r.json()["gera_patrimonio"] is False


class TestAtualizarItemEstoque:
    def test_edita_todos_os_campos(self, client):
        c, _ = client
        criado = c.post("/estoque/", json={
            "nome": "Antibiótico A", "categoria": "Medicamentos e produtos veterinários",
            "unidade": "ml", "quantidade": 100, "estoque_minimo": 10, "valor_unitario": 2.5,
        }).json()

        r = c.put(f"/estoque/{criado['id']}", json={
            "nome": "Antibiótico A (novo nome)", "categoria": "Medicamentos e produtos veterinários",
            "finalidade": "Medicamento", "unidade": "ml", "quantidade": 200, "estoque_minimo": 20,
            "valor_unitario": 3.0, "principio_ativo": "Oxitetraciclina",
        })
        assert r.status_code == 200, r.text
        atualizado = r.json()
        assert atualizado["nome"] == "Antibiótico A (novo nome)"
        assert atualizado["quantidade"] == 200
        assert atualizado["estoque_minimo"] == 20
        assert atualizado["valor_total"] == 600
        assert atualizado["abaixo_minimo"] is False
        assert atualizado["principio_ativo"] == "Oxitetraciclina"

    def test_edita_tipo_semen(self, client):
        c, _ = client
        criado = c.post("/estoque/", json={
            "nome": "Sêmen ABS 1", "categoria": "Sêmen e genética", "unidade": "dose",
            "quantidade": 5, "tipo_semen": "convencional",
        }).json()

        r = c.put(f"/estoque/{criado['id']}", json={
            "nome": "Sêmen ABS 1", "categoria": "Sêmen e genética", "unidade": "dose",
            "quantidade": 5, "tipo_semen": "sexado",
        })
        assert r.status_code == 200
        assert r.json()["tipo_semen"] == "sexado"

    def test_404_para_item_inexistente(self, client):
        c, _ = client
        r = c.put("/estoque/999", json={"nome": "Não existe", "unidade": "un"})
        assert r.status_code == 404

    def test_409_ao_renomear_para_nome_ja_usado(self, client):
        c, _ = client
        c.post("/estoque/", json={"nome": "Item 1", "unidade": "un"})
        item2 = c.post("/estoque/", json={"nome": "Item 2", "unidade": "un"}).json()

        r = c.put(f"/estoque/{item2['id']}", json={"nome": "Item 1", "unidade": "un"})
        assert r.status_code == 409


class TestExcluirItemEstoque:
    def test_exclui_item_sem_movimento(self, client):
        c, _ = client
        criado = c.post("/estoque/", json={"nome": "Item novo, nunca usado", "unidade": "un"}).json()

        r = c.delete(f"/estoque/{criado['id']}")
        assert r.status_code == 200, r.text
        assert r.json() == {"excluido": True}

        itens = c.get("/estoque/").json()["itens"]
        assert not any(i["id"] == criado["id"] for i in itens)

    def test_404_para_item_inexistente(self, client):
        c, _ = client
        r = c.delete("/estoque/9999")
        assert r.status_code == 404

    def test_409_com_movimento_vinculado_e_item_continua_existindo(self, client):
        c, _ = client
        criado = c.post("/estoque/", json={"nome": "Ração com movimento", "unidade": "kg", "quantidade": 0}).json()
        mov = c.post("/estoque/movimentar", json={
            "nome": "Ração com movimento", "movimento": "Entrada de ajuste", "quantidade": 10,
            "unidade": "kg", "data_movimento": "2026-08-01",
        })
        assert mov.status_code == 200, mov.text

        r = c.delete(f"/estoque/{criado['id']}")
        assert r.status_code == 409, r.text
        assert "Ração com movimento" in r.json()["detail"]

        itens = c.get("/estoque/").json()["itens"]
        assert any(i["id"] == criado["id"] for i in itens)
