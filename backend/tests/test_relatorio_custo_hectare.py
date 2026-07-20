"""
Testes do indicador "Custo por hectare" (Financeiro > Relatórios):
- cálculo puro (`fazenda.rules.custo_hectare.calcular_custo_por_hectare`);
- endpoint `GET /financeiro/custo-hectare`, que soma despesas de
  `ContaGerencial` no período (filtro opcional de centro de custo) e divide
  pela área total da fazenda (`ParametroFazenda.area_total_hectares`).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial, ParametroFazenda
from fazenda.rules.custo_hectare import calcular_custo_por_hectare


class TestCalcularCustoPorHectare:
    def test_divide_despesas_pela_area(self):
        r = calcular_custo_por_hectare(10_000.0, 50.0)
        assert r["despesas_total"] == 10_000.0
        assert r["area_hectares"] == 50.0
        assert r["custo_por_hectare"] == 200.0

    def test_area_zero_ou_none_da_custo_indefinido(self):
        assert calcular_custo_por_hectare(10_000.0, 0)["custo_por_hectare"] is None
        assert calcular_custo_por_hectare(10_000.0, None)["custo_por_hectare"] is None
        assert calcular_custo_por_hectare(10_000.0, 0)["area_hectares"] is None

    def test_arredonda_para_duas_casas(self):
        r = calcular_custo_por_hectare(1_000.0, 3.0)
        assert r["custo_por_hectare"] == 333.33


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # `parametros.get_param` (area_total_hectares) lê direto de
    # `fazenda.database.engine`, não da sessão injetada — precisa apontar
    # para o engine de teste (mesmo padrão de test_exclusoes.py/test_folha_rh.py).
    monkeypatch.setattr(database, "engine", engine)

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


class TestEndpointCustoHectare:
    def _sessao(self, engine):
        return Session(engine)

    def test_sem_area_configurada_custo_fica_indefinido(self, client):
        c, engine = client
        with self._sessao(engine) as session:
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00001", tipo="despesa", valor_total=1000.0,
                data_competencia=date(2026, 7, 10),
            ))
            session.commit()

        r = c.get("/financeiro/custo-hectare", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"})
        assert r.status_code == 200
        d = r.json()
        assert d["area_configurada"] is False
        assert d["despesas_total"] == 1000.0
        assert d["custo_por_hectare"] is None

    def test_com_area_configurada_calcula_custo_por_hectare(self, client):
        c, engine = client
        with self._sessao(engine) as session:
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00001", tipo="despesa", valor_total=2000.0,
                data_competencia=date(2026, 7, 10),
            ))
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00002", tipo="receita", valor_total=5000.0,
                data_competencia=date(2026, 7, 10),
            ))
            session.add(ParametroFazenda(
                chave="area_total_hectares", grupo="estrutura_fazenda",
                label="Área total da fazenda", valor="100", tipo="float", unidade="ha",
            ))
            session.commit()

        r = c.get("/financeiro/custo-hectare", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"})
        assert r.status_code == 200
        d = r.json()
        assert d["area_configurada"] is True
        assert d["despesas_total"] == 2000.0  # não conta a receita
        assert d["area_hectares"] == 100.0
        assert d["custo_por_hectare"] == 20.0

    def test_filtra_por_periodo_e_centro_custo(self, client):
        c, engine = client
        with self._sessao(engine) as session:
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00001", tipo="despesa", valor_total=1000.0,
                data_competencia=date(2026, 7, 10), centro_custo="Pecuária Leiteira",
            ))
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00002", tipo="despesa", valor_total=500.0,
                data_competencia=date(2026, 7, 10), centro_custo="Arrendamento",
            ))
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00003", tipo="despesa", valor_total=999.0,
                data_competencia=date(2026, 6, 10), centro_custo="Pecuária Leiteira",
            ))
            session.add(ParametroFazenda(
                chave="area_total_hectares", grupo="estrutura_fazenda",
                label="Área total da fazenda", valor="10", tipo="float", unidade="ha",
            ))
            session.commit()

        r = c.get("/financeiro/custo-hectare", params={
            "data_inicio": "2026-07-01", "data_fim": "2026-07-31", "centro_custo": "Pecuária Leiteira",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["despesas_total"] == 1000.0
        assert d["custo_por_hectare"] == 100.0
