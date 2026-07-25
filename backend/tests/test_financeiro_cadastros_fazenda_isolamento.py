"""
Isolamento por fazenda nos cadastros do Financeiro (Fase 3B) — Plano de
Contas Gerenciais, Tipo de Documento e Forma de Pagamento. Garante que duas
fazendas podem cadastrar o mesmo código/nome sem conflitar entre si, que uma
não vê o cadastro da outra, e que token legado (sem fazenda) continua vendo
tudo, exatamente como antes do retrofit multi-tenant.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Teste"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "outroadmin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestIsolamentoPlanoContas:
    def test_duas_fazendas_podem_cadastrar_o_mesmo_codigo(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/financeiro/plano-contas", json={"codigo": "9.99", "nome": "Conta fazenda 1"})
        assert r.status_code == 200, r.text

        _como_fazenda(2)
        r = c.post("/financeiro/plano-contas", json={"codigo": "9.99", "nome": "Conta fazenda 2"})
        assert r.status_code == 200, r.text

    def test_mesma_fazenda_nao_pode_repetir_codigo(self, client):
        c, _ = client
        _como_fazenda(1)
        c.post("/financeiro/plano-contas", json={"codigo": "9.98", "nome": "Primeira"})
        r = c.post("/financeiro/plano-contas", json={"codigo": "9.98", "nome": "Segunda"})
        assert r.status_code == 409

    def test_fazenda_1_nao_ve_plano_de_contas_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        c.post("/financeiro/plano-contas", json={"codigo": "9.97", "nome": "Só da fazenda 2"})

        _como_fazenda(1)
        r = c.get("/financeiro/plano-contas")
        assert r.status_code == 200
        codigos = {item["codigo"] for item in r.json()}
        assert "9.97" not in codigos

    def test_token_legado_sem_fazenda_ve_tudo(self, client):
        c, _ = client
        _como_fazenda(1)
        c.post("/financeiro/plano-contas", json={"codigo": "9.96", "nome": "Fazenda 1 legado"})
        _como_fazenda(2)
        c.post("/financeiro/plano-contas", json={"codigo": "9.95", "nome": "Fazenda 2 legado"})

        _como_fazenda(None)
        r = c.get("/financeiro/plano-contas")
        assert r.status_code == 200
        codigos = {item["codigo"] for item in r.json()}
        assert "9.96" in codigos
        assert "9.95" in codigos


class TestIsolamentoTipoDocumentoFormaPagamento:
    def test_duas_fazendas_podem_cadastrar_o_mesmo_nome_tipo_documento(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/financeiro/tipos-documento", json={"nome": "Recibo customizado"})
        assert r.status_code == 200, r.text

        _como_fazenda(2)
        r = c.post("/financeiro/tipos-documento", json={"nome": "Recibo customizado"})
        assert r.status_code == 200, r.text

    def test_mesma_fazenda_nao_pode_repetir_nome_tipo_documento(self, client):
        c, _ = client
        _como_fazenda(1)
        c.post("/financeiro/tipos-documento", json={"nome": "Nota especial"})
        r = c.post("/financeiro/tipos-documento", json={"nome": "Nota especial"})
        assert r.status_code == 409

    def test_fazenda_1_nao_ve_tipo_documento_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        c.post("/financeiro/tipos-documento", json={"nome": "Só fazenda 2"})

        _como_fazenda(1)
        r = c.get("/financeiro/tipos-documento")
        assert r.status_code == 200
        nomes = {item["nome"] for item in r.json()}
        assert "Só fazenda 2" not in nomes

    def test_duas_fazendas_podem_cadastrar_a_mesma_forma_pagamento(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/financeiro/formas-pagamento-cadastro", json={"nome": "cripto"})
        assert r.status_code == 200, r.text

        _como_fazenda(2)
        r = c.post("/financeiro/formas-pagamento-cadastro", json={"nome": "cripto"})
        assert r.status_code == 200, r.text

    def test_fazenda_1_nao_ve_forma_pagamento_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        c.post("/financeiro/formas-pagamento-cadastro", json={"nome": "vale-alimentacao"})

        _como_fazenda(1)
        r = c.get("/financeiro/formas-pagamento-cadastro")
        assert r.status_code == 200
        nomes = {item["nome"] for item in r.json()}
        assert "vale-alimentacao" not in nomes
