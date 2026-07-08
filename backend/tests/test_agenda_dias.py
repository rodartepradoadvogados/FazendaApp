"""
Testes do parâmetro `dias` da agenda — a janela de contas a pagar/receber
deve seguir o período pedido pelo front (não ficar travada em 10 dias).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        with Session(engine) as s:
            s.add(ContaGerencial(
                numero_lancamento="LC-2026-00001", tipo="despesa", descricao="Ração",
                data_vencimento=date(2026, 8, 15), valor_total=450.0, fornecedor_cliente="Fornecedor X",
            ))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestJanelaContasAPagar:
    def test_fora_da_janela_padrao_de_10_dias(self, client):
        r = client.get("/agenda/", params={"data": "2026-07-10"})
        eventos = r.json()["eventos"]
        assert not any(e["categoria"] == "Gestão/Financeiro" for e in eventos)

    def test_dentro_da_janela_ampliada(self, client):
        r = client.get("/agenda/", params={"data": "2026-07-10", "dias": 40})
        eventos = r.json()["eventos"]
        financeiros = [e for e in eventos if e["categoria"] == "Gestão/Financeiro"]
        assert len(financeiros) == 1
        assert financeiros[0]["ref"] == "LC-2026-00001"
