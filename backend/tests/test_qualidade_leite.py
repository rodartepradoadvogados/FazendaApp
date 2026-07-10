"""
Testes de Qualidade do leite (CCS/CBT/gordura/proteína/ST/ESD/lactose, por vaca
ou do tanque) e de Entrega mensal do leite ao laticínio.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import QualidadeLeite


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


class TestQualidadeLeite:
    def test_cria_leitura_do_tanque(self, client):
        c, engine = client
        r = c.post("/producao/qualidade-leite", json={
            "data_coleta": "2026-07-05", "ccs": 181, "cbt": 11, "gordura_pct": 3.69,
            "proteina_pct": 3.42, "solidos_totais_pct": 12.69, "esd_pct": 9.0, "lactose_pct": 4.69,
        })
        assert r.status_code == 201
        d = r.json()
        assert d["numero_matriz"] is None
        assert d["ccs"] == 181

    def test_cria_leitura_de_uma_vaca(self, client):
        c, engine = client
        r = c.post("/producao/qualidade-leite", json={"numero_matriz": "801", "data_coleta": "2026-07-05", "ccs": 900})
        assert r.status_code == 201
        assert r.json()["numero_matriz"] == "801"

    def test_lista_ordenada_por_data(self, client):
        c, engine = client
        c.post("/producao/qualidade-leite", json={"data_coleta": "2026-03-01", "ccs": 1})
        c.post("/producao/qualidade-leite", json={"data_coleta": "2026-01-01", "ccs": 2})
        r = c.get("/producao/qualidade-leite")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 2
        assert [x["data_coleta"] for x in d["registros"]] == ["2026-01-01", "2026-03-01"]


class TestEntregaLeiteMensal:
    def test_cria_entrega_do_mes(self, client):
        c, engine = client
        r = c.post("/producao/entrega-leite", json={"competencia": "2026-06", "quantidade_litros": 12000})
        assert r.status_code == 201
        assert r.json()["quantidade_litros"] == 12000

    def test_relanca_mesma_competencia_atualiza_em_vez_de_duplicar(self, client):
        c, engine = client
        c.post("/producao/entrega-leite", json={"competencia": "2026-06", "quantidade_litros": 12000})
        c.post("/producao/entrega-leite", json={"competencia": "2026-06", "quantidade_litros": 12500})
        r = c.get("/producao/entrega-leite")
        d = r.json()
        assert d["total"] == 1
        assert d["registros"][0]["quantidade_litros"] == 12500
