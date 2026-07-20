"""
Testes de Qualidade do leite (CCS/CBT/gordura/proteína/ST/ESD/lactose, por vaca
ou do tanque), de Entrega mensal do leite ao laticínio e das faixas de
bonificação/penalização por qualidade (#548).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import QualidadeLeite
from fazenda.rules.bonificacao_qualidade import calcular_bonificacao


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


class TestCalcularBonificacao:
    """Unidade pura de fazenda/rules/bonificacao_qualidade.py — sem faixas
    cadastradas, sem HTTP, só a lógica de comparar valor × faixa."""

    class _Faixa:
        def __init__(self, indicador, valor_min=None, valor_max=None, ajuste_por_litro=0.0, ativo=True):
            self.indicador = indicador
            self.valor_min = valor_min
            self.valor_max = valor_max
            self.ajuste_por_litro = ajuste_por_litro
            self.ativo = ativo

    def test_sem_faixas_cadastradas_devolve_none(self):
        r = calcular_bonificacao({"ccs": 150, "cbt": 20}, [])
        assert r["total_por_litro"] is None
        assert r["detalhe"] == []

    def test_sem_faixas_ativas_devolve_none(self):
        faixas = [self._Faixa("ccs", valor_max=200, ajuste_por_litro=0.02, ativo=False)]
        r = calcular_bonificacao({"ccs": 150}, faixas)
        assert r["total_por_litro"] is None

    def test_bonificacao_por_ccs_baixo(self):
        faixas = [
            self._Faixa("ccs", valor_max=200, ajuste_por_litro=0.02),
            self._Faixa("ccs", valor_min=200.01, valor_max=400, ajuste_por_litro=0.0),
            self._Faixa("ccs", valor_min=400.01, ajuste_por_litro=-0.05),
        ]
        r = calcular_bonificacao({"ccs": 181}, faixas)
        assert r["total_por_litro"] == 0.02
        assert r["detalhe"] == [{"indicador": "ccs", "valor": 181, "ajuste_por_litro": 0.02}]

    def test_penalizacao_por_ccs_alto(self):
        faixas = [
            self._Faixa("ccs", valor_max=200, ajuste_por_litro=0.02),
            self._Faixa("ccs", valor_min=400.01, ajuste_por_litro=-0.05),
        ]
        r = calcular_bonificacao({"ccs": 900}, faixas)
        assert r["total_por_litro"] == -0.05

    def test_soma_varios_indicadores(self):
        faixas = [
            self._Faixa("ccs", valor_max=200, ajuste_por_litro=0.02),
            self._Faixa("cbt", valor_max=50, ajuste_por_litro=0.015),
            self._Faixa("gordura_pct", valor_min=3.5, ajuste_por_litro=0.01),
        ]
        r = calcular_bonificacao({"ccs": 150, "cbt": 30, "gordura_pct": 3.69, "proteina_pct": 3.0}, faixas)
        assert r["total_por_litro"] == 0.045
        assert {d["indicador"] for d in r["detalhe"]} == {"ccs", "cbt", "gordura_pct"}

    def test_valor_nulo_no_indicador_nao_conta(self):
        faixas = [self._Faixa("ccs", valor_max=200, ajuste_por_litro=0.02)]
        r = calcular_bonificacao({"ccs": None}, faixas)
        assert r["total_por_litro"] == 0.0
        assert r["detalhe"] == []

    def test_valor_fora_de_qualquer_faixa_nao_aplica_ajuste(self):
        faixas = [self._Faixa("ccs", valor_min=0, valor_max=100, ajuste_por_litro=0.02)]
        r = calcular_bonificacao({"ccs": 500}, faixas)
        assert r["total_por_litro"] == 0.0
        assert r["detalhe"] == []


class TestFaixasBonificacaoQualidadeApi:
    def test_lista_vazia_sem_faixas_cadastradas(self, client):
        c, engine = client
        r = c.get("/producao/faixas-bonificacao-qualidade")
        assert r.status_code == 200
        assert r.json() == {"faixas": []}

    def test_cria_faixa(self, client):
        c, engine = client
        r = c.post("/producao/faixas-bonificacao-qualidade", json={
            "indicador": "ccs", "valor_max": 200, "ajuste_por_litro": 0.02,
        })
        assert r.status_code == 201
        d = r.json()
        assert d["indicador"] == "ccs"
        assert d["ajuste_por_litro"] == 0.02
        assert d["ativo"] is True

    def test_rejeita_indicador_invalido(self, client):
        c, engine = client
        r = c.post("/producao/faixas-bonificacao-qualidade", json={
            "indicador": "ph_do_leite", "ajuste_por_litro": 0.01,
        })
        assert r.status_code == 400

    def test_rejeita_min_maior_que_max(self, client):
        c, engine = client
        r = c.post("/producao/faixas-bonificacao-qualidade", json={
            "indicador": "cbt", "valor_min": 100, "valor_max": 50, "ajuste_por_litro": -0.01,
        })
        assert r.status_code == 400

    def test_atualiza_faixa(self, client):
        c, engine = client
        criado = c.post("/producao/faixas-bonificacao-qualidade", json={
            "indicador": "cbt", "valor_max": 50, "ajuste_por_litro": 0.015,
        }).json()
        r = c.put(f"/producao/faixas-bonificacao-qualidade/{criado['id']}", json={
            "indicador": "cbt", "valor_max": 50, "ajuste_por_litro": 0.03, "ativo": False,
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ajuste_por_litro"] == 0.03
        assert d["ativo"] is False

    def test_atualizar_faixa_inexistente_404(self, client):
        c, engine = client
        r = c.put("/producao/faixas-bonificacao-qualidade/999", json={"indicador": "ccs", "ajuste_por_litro": 0.01})
        assert r.status_code == 404

    def test_exclui_faixa(self, client):
        c, engine = client
        criado = c.post("/producao/faixas-bonificacao-qualidade", json={
            "indicador": "ccs", "valor_max": 200, "ajuste_por_litro": 0.02,
        }).json()
        r = c.delete(f"/producao/faixas-bonificacao-qualidade/{criado['id']}")
        assert r.status_code == 200
        assert c.get("/producao/faixas-bonificacao-qualidade").json() == {"faixas": []}


class TestQualidadeLeiteComBonificacao:
    def test_sem_faixas_cadastradas_bonificacao_e_none(self, client):
        c, engine = client
        c.post("/producao/qualidade-leite", json={"data_coleta": "2026-07-05", "ccs": 181, "cbt": 11})
        r = c.get("/producao/qualidade-leite")
        d = r.json()
        assert d["tem_faixas_bonificacao"] is False
        assert d["registros"][0]["bonificacao_por_litro"] is None
        assert d["registros"][0]["bonificacao_detalhe"] == []

    def test_com_faixas_cadastradas_calcula_bonificacao_do_lancamento(self, client):
        c, engine = client
        c.post("/producao/faixas-bonificacao-qualidade", json={
            "indicador": "ccs", "valor_max": 200, "ajuste_por_litro": 0.02,
        })
        c.post("/producao/faixas-bonificacao-qualidade", json={
            "indicador": "cbt", "valor_max": 50, "ajuste_por_litro": 0.015,
        })
        c.post("/producao/qualidade-leite", json={"data_coleta": "2026-07-05", "ccs": 181, "cbt": 11})
        r = c.get("/producao/qualidade-leite")
        d = r.json()
        assert d["tem_faixas_bonificacao"] is True
        reg = d["registros"][0]
        assert reg["bonificacao_por_litro"] == 0.035
        assert {x["indicador"] for x in reg["bonificacao_detalhe"]} == {"ccs", "cbt"}

    def test_faixa_inativa_nao_conta_para_tem_faixas_bonificacao(self, client):
        c, engine = client
        criado = c.post("/producao/faixas-bonificacao-qualidade", json={
            "indicador": "ccs", "valor_max": 200, "ajuste_por_litro": 0.02,
        }).json()
        c.put(f"/producao/faixas-bonificacao-qualidade/{criado['id']}", json={
            "indicador": "ccs", "valor_max": 200, "ajuste_por_litro": 0.02, "ativo": False,
        })
        c.post("/producao/qualidade-leite", json={"data_coleta": "2026-07-05", "ccs": 181})
        r = c.get("/producao/qualidade-leite")
        d = r.json()
        assert d["tem_faixas_bonificacao"] is False
        assert d["registros"][0]["bonificacao_por_litro"] is None
