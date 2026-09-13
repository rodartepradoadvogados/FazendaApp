"""
GET /financeiro/ultimo-preco — mini-observação de "último valor unitário
pago" abaixo do item selecionado em Contas a pagar (ver FormFinanceiro.tsx,
bloco de item). Cobre os três requisitos de B9-B12: com histórico devolve o
lançamento mais recente, sem histórico devolve vazio (nunca inventa 0,00), e
isolamento por fazenda (item de uma fazenda não vaza pro cálculo de outra).
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

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


def _lancar(c, produto: str, valor_unitario: float, data_emissao: str, valor_total: float | None = None):
    payload = {
        "tipo": "despesa",
        "itens": [{"produto": produto, "valor_unitario": valor_unitario, "valor_total": valor_total or valor_unitario}],
        "centro_custo": "Pecuária Leiteira",
        "data_emissao": data_emissao,
        "data_vencimento": data_emissao,
        "parcelas": [],
        "data_pagamento": None,
    }
    r = c.post("/financeiro/lancamentos", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestUltimoPreco:
    def test_com_historico_devolve_o_mais_recente(self, client):
        c, _ = client
        _como_fazenda(1)
        _lancar(c, "Ração para gado", 100.0, "2026-01-10")
        _lancar(c, "Ração para gado", 130.0, "2026-06-15")
        _lancar(c, "Ração para gado", 115.0, "2026-03-20")

        r = c.get("/financeiro/ultimo-preco", params={"produto": "Ração para gado"})
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["valor_unitario"] == 130.0
        assert corpo["data"] == "2026-06-15"
        assert corpo["produto"] == "Ração para gado"
        assert corpo["numero_lancamento"]

    def test_sem_historico_devolve_vazio(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.get("/financeiro/ultimo-preco", params={"produto": "Produto nunca comprado"})
        assert r.status_code == 200
        assert r.json() == {}

    def test_produto_de_outra_fazenda_nao_vaza(self, client):
        c, _ = client
        _como_fazenda(1)
        _lancar(c, "Sal mineral", 40.0, "2026-02-01")

        _como_fazenda(2)
        r = c.get("/financeiro/ultimo-preco", params={"produto": "Sal mineral"})
        assert r.status_code == 200
        assert r.json() == {}

    def test_casamento_ignora_maiuscula_e_espacos_nas_pontas(self, client):
        c, _ = client
        _como_fazenda(1)
        _lancar(c, "Adubo NPK", 200.0, "2026-04-05")

        r = c.get("/financeiro/ultimo-preco", params={"produto": "  adubo npk  "})
        assert r.status_code == 200
        assert r.json()["valor_unitario"] == 200.0

    def test_sem_parametro_devolve_vazio(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.get("/financeiro/ultimo-preco", params={"produto": "   "})
        assert r.status_code == 200
        assert r.json() == {}
