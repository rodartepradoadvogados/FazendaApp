"""
Custo por vaca e por lote — Financeiro > Relatórios (GET /financeiro/custo-vaca-lote).
Mesmo padrão de test_relatorio_custo_hectare.py.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ContaGerencial, ControleLeiteiro
from fazenda.rules.custo_producao import calcular_custo_por_lote, calcular_custo_por_vaca


def test_calcular_custo_por_vaca():
    assert calcular_custo_por_vaca(10000.0, 20) == {
        "num_vacas": 20, "despesas_total": 10000.0, "custo_por_vaca": 500.0,
    }


def test_calcular_custo_por_vaca_sem_vacas():
    assert calcular_custo_por_vaca(10000.0, 0)["custo_por_vaca"] is None


def test_calcular_custo_por_lote_rateia_proporcional():
    linhas = calcular_custo_por_lote(1000.0, {"01 - Alta": 6, "02 - Baixa": 4})
    assert linhas == [
        {"lote": "01 - Alta", "num_vacas": 6, "custo_alocado": 600.0, "custo_por_vaca": 100.0},
        {"lote": "02 - Baixa", "num_vacas": 4, "custo_alocado": 400.0, "custo_por_vaca": 100.0},
    ]


def test_calcular_custo_por_lote_ignora_lote_vazio():
    linhas = calcular_custo_por_lote(1000.0, {"01": 10, "02": 0})
    assert [l["lote"] for l in linhas] == ["01"]


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


def test_endpoint_calcula_por_lote_e_total(client):
    c, engine = client
    with Session(engine) as s:
        s.add(Animal(numero="1", grupo_primario="01 - Alta"))
        s.add(Animal(numero="2", grupo_primario="01 - Alta"))
        s.add(Animal(numero="3", grupo_primario="02 - Baixa"))
        s.add(ControleLeiteiro(numero_matriz="1", data_controle=date(2026, 7, 5), producao_kg=30))
        s.add(ControleLeiteiro(numero_matriz="2", data_controle=date(2026, 7, 10), producao_kg=25))
        s.add(ControleLeiteiro(numero_matriz="3", data_controle=date(2026, 7, 15), producao_kg=20))
        s.add(ContaGerencial(tipo="despesa", centro_custo="Pecuária Leiteira", data_competencia=date(2026, 7, 20), valor_total=3000.0))
        s.add(ContaGerencial(tipo="despesa", centro_custo="Arrendamento", data_competencia=date(2026, 7, 20), valor_total=99999.0))
        s.commit()

    r = c.get("/financeiro/custo-vaca-lote", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["num_vacas"] == 3
    assert d["despesas_total"] == 3000.0
    assert d["custo_por_vaca"] == 1000.0
    assert d["tem_vacas_no_periodo"] is True
    por_lote = {l["lote"]: l for l in d["por_lote"]}
    assert por_lote["01 - Alta"]["num_vacas"] == 2
    assert por_lote["01 - Alta"]["custo_alocado"] == 2000.0
    assert por_lote["02 - Baixa"]["num_vacas"] == 1
    assert por_lote["02 - Baixa"]["custo_alocado"] == 1000.0


def test_endpoint_sem_controle_leiteiro_no_periodo(client):
    c, engine = client
    with Session(engine) as s:
        s.add(ContaGerencial(tipo="despesa", centro_custo="Pecuária Leiteira", data_competencia=date(2026, 7, 20), valor_total=3000.0))
        s.commit()

    r = c.get("/financeiro/custo-vaca-lote", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["num_vacas"] == 0
    assert d["custo_por_vaca"] is None
    assert d["tem_vacas_no_periodo"] is False
    assert d["por_lote"] == []


def test_endpoint_filtra_por_centro_custo_customizado(client):
    c, engine = client
    with Session(engine) as s:
        s.add(Animal(numero="1", grupo_primario="01"))
        s.add(ControleLeiteiro(numero_matriz="1", data_controle=date(2026, 7, 5), producao_kg=30))
        s.add(ContaGerencial(tipo="despesa", centro_custo="Arrendamento", data_competencia=date(2026, 7, 20), valor_total=500.0))
        s.commit()

    r = c.get("/financeiro/custo-vaca-lote", params={
        "data_inicio": "2026-07-01", "data_fim": "2026-07-31", "centro_custo": "Arrendamento",
    })
    assert r.status_code == 200, r.text
    assert r.json()["despesas_total"] == 500.0
