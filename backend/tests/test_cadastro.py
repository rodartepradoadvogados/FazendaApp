"""
Testes do router de Cadastro — fornecedores, ficha do animal e metadados de
itens de estoque (Configurações > Cadastro).
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


class TestFornecedores:
    def test_criar_listar_atualizar(self, client):
        c, engine = client
        r = c.post("/cadastro/fornecedores", json={"nome": "Agropecuária Central", "tipo": "fornecedor"})
        assert r.status_code == 200
        fid = r.json()["id"]

        r = c.get("/cadastro/fornecedores")
        assert len(r.json()) == 1

        r = c.put(f"/cadastro/fornecedores/{fid}", json={"nome": "Agropecuária Central Ltda", "tipo": "fabricante"})
        assert r.status_code == 200
        assert r.json()["nome"] == "Agropecuária Central Ltda"
        assert r.json()["tipo"] == "fabricante"

    def test_tipo_invalido_rejeitado(self, client):
        c, engine = client
        r = c.post("/cadastro/fornecedores", json={"nome": "X", "tipo": "invalido"})
        assert r.status_code == 400

    def test_nome_vazio_rejeitado(self, client):
        c, engine = client
        r = c.post("/cadastro/fornecedores", json={"nome": "  ", "tipo": "cliente"})
        assert r.status_code == 400


class TestFichaAnimal:
    def test_criar_animal_grava_na_tabela_real(self, client):
        c, engine = client
        r = c.post("/cadastro/animais", json={"numero": "500", "nome": "Estrela", "sexo": "F", "raca": "Girolando"})
        assert r.status_code == 200
        d = r.json()
        assert d["numero"] == "500"
        assert d["nome"] == "Estrela"
        assert d["ativo"] is True

        # O mesmo animal aparece no endpoint real de animais usado no resto do site.
        r2 = c.get("/animais/")
        assert any(a["numero"] == "500" for a in r2.json())

    def test_numero_duplicado_rejeitado(self, client):
        c, engine = client
        c.post("/cadastro/animais", json={"numero": "501"})
        r = c.post("/cadastro/animais", json={"numero": "501"})
        assert r.status_code == 400

    def test_atualizar_ficha_e_baixa_desativa(self, client):
        c, engine = client
        c.post("/cadastro/animais", json={"numero": "502"})
        r = c.put("/cadastro/animais/502", json={"numero": "502", "motivo_baixa": "venda", "data_baixa": "2026-07-01"})
        assert r.status_code == 200
        assert r.json()["ativo"] is False
        assert r.json()["motivo_baixa"] == "venda"

    def test_animal_inexistente_404(self, client):
        c, engine = client
        r = c.put("/cadastro/animais/999", json={"numero": "999"})
        assert r.status_code == 404


class TestMetaEstoque:
    def test_atualizar_metadados_ensacado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Ração concentrada", categoria="alimento", quantidade=100))
            s.commit()
        r = c.get("/cadastro/estoque-itens")
        item_id = r.json()[0]["id"]

        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"ensacado": True, "kg_por_saco": 40.0})
        assert r.status_code == 200
        assert r.json()["ensacado"] is True
        assert r.json()["kg_por_saco"] == 40.0

    def test_fornecedor_inexistente_rejeitado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Sal mineral", categoria="alimento", quantidade=10))
            s.commit()
        item_id = c.get("/cadastro/estoque-itens").json()[0]["id"]
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"fornecedor_id": 999})
        assert r.status_code == 400
