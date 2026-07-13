"""
Testes do relatório Controle leiteiro × Entregue no período: média diária do
controle projetada, entrega/receita rateadas por dias do mês, consumo de leite
dos bezerros pela dieta lançada e residual da equipe/família.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial, ControleLeiteiro, DietaLancamento, EntregaLeiteMensal


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


class TestRelatorioControleEntrega:
    def test_projeta_controle_entrega_bezerros_e_equipe(self, client):
        c, engine = client
        with Session(engine) as s:
            # 2 dias com controle no período: 600 kg e 620 kg (média 610/dia).
            s.add(ControleLeiteiro(numero_matriz="1", data_controle=date(2026, 7, 5), producao_kg=600))
            s.add(ControleLeiteiro(numero_matriz="1", data_controle=date(2026, 7, 15), producao_kg=620))
            # Entrega mensal de julho: 15500 kg → 15500/31 = 500 kg/dia.
            s.add(EntregaLeiteMensal(competencia="2026-07", quantidade_litros=15500))
            # Receita do laticínio em julho.
            s.add(ContaGerencial(tipo="receita", fornecedor_cliente="ITALAC", data_competencia=date(2026, 7, 31), valor_total=31000))
            # Dieta ativa com 100 kg/dia de leite para bezerros.
            s.add(DietaLancamento(lote=6, data_abertura=date(2026, 6, 1), leite_bezerros_kg_dia=100))
            s.commit()

        r = c.get("/producao/relatorio-controle-entrega", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["dias_periodo"] == 31
        assert d["dias_com_controle"] == 2
        assert d["media_diaria_controle_kg"] == 610.0
        assert d["controle_projetado_kg"] == 610.0 * 31       # 18910
        assert d["entrega_projetada_kg"] == 15500.0           # 500/dia × 31 dias
        assert d["receita_projetada"] == 31000.0
        assert d["nao_entregue_kg"] == round(18910.0 - 15500.0, 1)   # 3410
        assert d["leite_bezerros_kg_dia"] == 100.0
        assert d["bezerros_kg"] == 100.0 * 31                 # 3100
        assert d["bezerros_fonte"] == "dieta_lancada"
        assert d["equipe_kg"] == round(3410.0 - 3100.0, 1)    # 310
        # Desvio padrão % (CV) baixo — produção estável (600 e 620).
        assert d["desvio_padrao_pct"] is not None and d["desvio_padrao_pct"] < 5

    def test_entrega_parcial_do_mes_e_rateio_por_dias(self, client):
        """Período de meio mês: entrega rateada por dias do mês × dias do período."""
        c, engine = client
        with Session(engine) as s:
            s.add(ControleLeiteiro(numero_matriz="1", data_controle=date(2026, 2, 10), producao_kg=500))
            # Fevereiro de 2026 tem 28 dias; 2800 kg → 100 kg/dia.
            s.add(EntregaLeiteMensal(competencia="2026-02", quantidade_litros=2800))
            s.commit()

        # Período de 10 dias dentro de fevereiro.
        r = c.get("/producao/relatorio-controle-entrega", params={"data_inicio": "2026-02-01", "data_fim": "2026-02-10"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["dias_periodo"] == 10
        assert d["entrega_projetada_kg"] == 1000.0    # 100 kg/dia × 10 dias
