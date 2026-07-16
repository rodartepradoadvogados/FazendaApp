"""
Financeiro: detecção de lançamento parecido (possível duplicado) — #395.
GET /financeiro/possiveis-duplicados compara fornecedor/cliente + valor
(tolerância) + data (janela de dias) contra lançamentos já existentes.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — garante que as tabelas estejam registradas no metadata antes do create_all


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


def _criar(c, fornecedor="Agropecuária Central", valor=900.0, data="2026-07-10", tipo="despesa"):
    r = c.post("/financeiro/lancamentos", json={
        "tipo": tipo, "fornecedor_cliente": fornecedor, "data_emissao": data,
        "itens": [{"produto": "Ração", "valor_total": valor}],
    })
    assert r.status_code == 201
    return r.json()


class TestPossiveisDuplicados:
    def test_encontra_parecido_por_fornecedor_valor_e_data(self, client):
        c, _ = client
        _criar(c)
        r = c.get("/financeiro/possiveis-duplicados", params={
            "tipo": "despesa", "valor_total": 900.0, "fornecedor_cliente": "Agropecuária Central", "data_emissao": "2026-07-12",
        })
        assert r.status_code == 200
        achados = r.json()
        assert len(achados) == 1
        assert achados[0]["fornecedor_cliente"] == "Agropecuária Central"

    def test_fornecedor_diferente_nao_e_duplicado(self, client):
        c, _ = client
        _criar(c, fornecedor="Agropecuária Central")
        r = c.get("/financeiro/possiveis-duplicados", params={
            "tipo": "despesa", "valor_total": 900.0, "fornecedor_cliente": "Outro Fornecedor", "data_emissao": "2026-07-10",
        })
        assert r.json() == []

    def test_valor_fora_da_tolerancia_nao_e_duplicado(self, client):
        c, _ = client
        _criar(c, valor=900.0)
        r = c.get("/financeiro/possiveis-duplicados", params={
            "tipo": "despesa", "valor_total": 1200.0, "fornecedor_cliente": "Agropecuária Central", "data_emissao": "2026-07-10",
        })
        assert r.json() == []

    def test_data_fora_da_janela_nao_e_duplicado(self, client):
        c, _ = client
        _criar(c, data="2026-07-10")
        r = c.get("/financeiro/possiveis-duplicados", params={
            "tipo": "despesa", "valor_total": 900.0, "fornecedor_cliente": "Agropecuária Central", "data_emissao": "2026-09-01",
        })
        assert r.json() == []

    def test_tipo_diferente_nao_e_duplicado(self, client):
        c, _ = client
        _criar(c, tipo="despesa")
        r = c.get("/financeiro/possiveis-duplicados", params={
            "tipo": "receita", "valor_total": 900.0, "fornecedor_cliente": "Agropecuária Central", "data_emissao": "2026-07-10",
        })
        assert r.json() == []

    def test_lancamento_parcelado_aparece_uma_so_vez(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "fornecedor_cliente": "Agropecuária Central", "data_emissao": "2026-07-10",
            "itens": [{"produto": "Ração", "valor_total": 900.0}],
            "parcelas": [{"data_vencimento": "2026-08-10", "valor": 450.0}, {"data_vencimento": "2026-09-10", "valor": 450.0}],
        })
        assert r.status_code == 201
        r2 = c.get("/financeiro/possiveis-duplicados", params={
            "tipo": "despesa", "valor_total": 450.0, "fornecedor_cliente": "Agropecuária Central", "data_emissao": "2026-07-10",
        })
        assert len(r2.json()) == 1
