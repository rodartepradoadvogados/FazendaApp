"""Categoria N:N de Fornecedor (Cadastro > Estoque) — CRUD + isolamento por fazenda."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

import pytest
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, Fornecedor
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.add(Fornecedor(id=1, fazenda_id=1, nome="Fornecedor A", tipo="fornecedor"))
        s.add(Fornecedor(id=2, fazenda_id=2, nome="Fornecedor B", tipo="fornecedor"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "admin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestCrud:
    def test_adicionar_listar_remover(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/cadastro/fornecedores/1/categorias", json={"categoria": "Ração e insumos alimentares"})
        assert r.status_code == 201, r.text
        categoria_id = r.json()["id"]

        r2 = c.post("/cadastro/fornecedores/1/categorias", json={"categoria": "Sêmen e genética"})
        assert r2.status_code == 201

        listagem = c.get("/cadastro/fornecedores/1/categorias")
        assert len(listagem.json()) == 2

        remover = c.delete(f"/cadastro/fornecedores/1/categorias/{categoria_id}")
        assert remover.status_code == 204
        assert len(c.get("/cadastro/fornecedores/1/categorias").json()) == 1

    def test_adicionar_categoria_repetida_e_idempotente(self, client):
        c, _ = client
        _como_fazenda(1)
        c.post("/cadastro/fornecedores/1/categorias", json={"categoria": "Ração e insumos alimentares"})
        c.post("/cadastro/fornecedores/1/categorias", json={"categoria": "Ração e insumos alimentares"})
        assert len(c.get("/cadastro/fornecedores/1/categorias").json()) == 1

    def test_categoria_vazia_e_recusada(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/cadastro/fornecedores/1/categorias", json={"categoria": "   "})
        assert r.status_code == 400


class TestIsolamento:
    def test_fazenda_2_nao_enxerga_nem_altera_fornecedor_da_fazenda_1(self, client):
        c, _ = client
        _como_fazenda(1)
        c.post("/cadastro/fornecedores/1/categorias", json={"categoria": "Ração e insumos alimentares"})

        _como_fazenda(2)
        assert c.get("/cadastro/fornecedores/1/categorias").status_code == 404
        assert c.post("/cadastro/fornecedores/1/categorias", json={"categoria": "Outra"}).status_code == 404

    def test_nao_remove_categoria_de_fornecedor_de_outra_fazenda_por_id_advinhado(self, client):
        c, _ = client
        _como_fazenda(1)
        categoria_id = c.post("/cadastro/fornecedores/1/categorias", json={"categoria": "Ração e insumos alimentares"}).json()["id"]

        _como_fazenda(2)
        c.post("/cadastro/fornecedores/2/categorias", json={"categoria": "Sêmen e genética"})
        # Fazenda Dois tenta excluir a categoria (id sequencial global) via o
        # PRÓPRIO fornecedor (2) — a linha pertence ao fornecedor 1, então
        # tem que ser recusada mesmo o fornecedor sendo da fazenda certa.
        assert c.delete(f"/cadastro/fornecedores/2/categorias/{categoria_id}").status_code == 404

        _como_fazenda(1)
        assert len(c.get("/cadastro/fornecedores/1/categorias").json()) == 1
