"""
Testes do relatório que compara controle leiteiro × entrega mensal × receita
da ITALAC (contas gerenciais) e projeta o consumo de leite pelas bezerras/
bezerros a partir da dieta atual.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ContaGerencial, ControleLeiteiro, Dieta, EntregaLeiteMensal, LancamentoItem


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


class TestRelatorioLeiteItalac:
    def test_relatorio_cruza_fontes_e_projeta_consumo_bezerros(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(ControleLeiteiro(numero_matriz="801", data_controle=date(2026, 6, 10), producao_kg=30))
            s.add(ControleLeiteiro(numero_matriz="802", data_controle=date(2026, 6, 15), producao_kg=25))
            s.add(EntregaLeiteMensal(competencia="2026-06", quantidade_litros=1000))
            s.add(ContaGerencial(
                tipo="receita", fornecedor_cliente="Italac Laticínios",
                data_competencia=date(2026, 6, 20), quantidade=1000, valor_total=2000,
            ))
            s.add(Animal(numero="B1", categoria_abrev="BEZ", categoria_completa="Bezerra", grupo_primario="06 - BEZERRAS", ativo=True, sexo="F"))
            s.add(Animal(numero="B2", categoria_abrev="BEZ", categoria_completa="Bezerro", grupo_primario="06 - BEZERRAS", ativo=True, sexo="M"))
            s.add(Dieta(lote=6, categoria="Bezerra", ingrediente="Leite", quantidade=4, unidade="L"))
            s.commit()

        r = c.get("/producao/relatorio-leite-italac")
        assert r.status_code == 200
        d = r.json()
        assert d["efetivo_bezerros"] == 2
        assert d["consumo_bezerros_dia_litros"] == 8.0
        assert d["consumo_bezerros_mes_litros"] == 240.0

        linhas = {l["competencia"]: l for l in d["linhas"]}
        junho = linhas["2026-06"]
        assert junho["controle_leiteiro_kg"] == 55
        assert junho["entrega_litros"] == 1000
        assert junho["italac_litros"] == 1000
        assert junho["italac_receita"] == 2000
        assert junho["preco_medio_litro"] == 2.0

    def test_lancamento_manual_usa_quantidade_do_item(self, client):
        """Lançamento manual não preenche quantidade na conta — cai para a soma dos itens da nota."""
        c, engine = client
        with Session(engine) as s:
            s.add(ContaGerencial(
                numero_lancamento="LC-2026-00099", tipo="receita", fornecedor_cliente="Italac Laticínios",
                data_competencia=date(2026, 7, 1), quantidade=None, valor_total=240,
            ))
            s.add(LancamentoItem(numero_lancamento="LC-2026-00099", tipo="receita", produto="Leite", quantidade=100, valor_total=240))
            s.commit()

        r = c.get("/producao/relatorio-leite-italac")
        assert r.status_code == 200
        linhas = {l["competencia"]: l for l in r.json()["linhas"]}
        assert linhas["2026-07"]["italac_litros"] == 100
        assert linhas["2026-07"]["italac_receita"] == 240
