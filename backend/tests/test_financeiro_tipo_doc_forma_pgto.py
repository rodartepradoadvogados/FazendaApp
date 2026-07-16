"""
Cadastro de Tipo de documento e Forma de pagamento (Configurações > Parâmetros
financeiros) — substituem as listas fixas TIPOS_DOCUMENTO/FORMAS_PAGAMENTO —
e o campo forma_pagamento no lançamento com pagamento imediato (jaPago).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, FormaPagamentoCadastro, TipoDocumento


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
        c.engine = engine
        yield c

    main.app.dependency_overrides.clear()


def test_crud_tipos_documento(client):
    resp = client.post("/financeiro/tipos-documento", json={"nome": "Ordem de serviço", "ativo": True})
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    resp = client.get("/financeiro/tipos-documento")
    assert resp.status_code == 200
    assert any(t["nome"] == "Ordem de serviço" for t in resp.json())

    resp = client.put(f"/financeiro/tipos-documento/{item_id}", json={"nome": "Ordem de serviço", "ativo": False})
    assert resp.status_code == 200
    assert resp.json()["ativo"] is False

    client.post("/financeiro/tipos-documento", json={"nome": "Fatura"})
    resp = client.post("/financeiro/tipos-documento", json={"nome": "Fatura"})
    assert resp.status_code == 409


def test_crud_formas_pagamento(client):
    resp = client.post("/financeiro/formas-pagamento-cadastro", json={"nome": "dinheiro", "ativo": True})
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    resp = client.get("/financeiro/formas-pagamento-cadastro")
    assert resp.status_code == 200
    assert any(f["nome"] == "dinheiro" for f in resp.json())

    resp = client.put(f"/financeiro/formas-pagamento-cadastro/{item_id}", json={"nome": "dinheiro", "ativo": False})
    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


def test_opcoes_le_cadastro_com_fallback_para_lista_fixa(client):
    resp = client.get("/financeiro/opcoes")
    assert resp.status_code == 200
    dados = resp.json()
    # Sem nada cadastrado, cai na lista fixa antiga.
    assert "Nota fiscal" in dados["tipos_documento"]
    assert "pix" in dados["formas_pagamento"]

    client.post("/financeiro/tipos-documento", json={"nome": "Ordem de serviço"})
    resp = client.get("/financeiro/opcoes")
    dados = resp.json()
    # Com cadastro, usa só os cadastrados (ativos).
    assert dados["tipos_documento"] == ["Ordem de serviço"]


def test_lancamento_ja_pago_grava_forma_pagamento(client):
    resp = client.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Ração", "quantidade": 1, "valor_unitario": 100.0, "valor_total": 100.0}],
        "data_emissao": "2026-07-01",
        "data_pagamento": "2026-07-01",
        "valor_pago": 100.0,
        "forma_pagamento": "pix",
    })
    assert resp.status_code in (200, 201), resp.text

    with Session(client.engine) as session:
        registro = session.exec(select(ContaGerencial)).first()
        assert registro is not None
        assert registro.forma_pagamento == "pix"
