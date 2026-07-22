"""
Testes da Opção A do plano de custo agrícola (silagem):
- cadastro de Safra (CRUD, GET/POST/PUT /safras/);
- cálculo puro (`fazenda.rules.custo_safra.calcular_custo_safra`);
- endpoint `GET /financeiro/custo-safra`, que soma despesas de
  `ContaGerencial` no centro de custo e período da safra, divide pelo
  hectare/tonelada cadastrados e quebra por categoria (nível 1 do código).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial, Safra
from fazenda.rules.custo_safra import calcular_custo_safra


class TestCalcularCustoSafra:
    def test_divide_despesas_por_hectare_e_tonelada(self):
        r = calcular_custo_safra(20_000.0, 100.0, 50.0)
        assert r["despesas_total"] == 20_000.0
        assert r["hectares"] == 100.0
        assert r["toneladas_produzidas"] == 50.0
        assert r["custo_por_hectare"] == 200.0
        assert r["custo_por_tonelada"] == 400.0

    def test_hectare_ou_tonelada_zero_ou_none_da_custo_indefinido(self):
        assert calcular_custo_safra(1000.0, 0, 10)["custo_por_hectare"] is None
        assert calcular_custo_safra(1000.0, None, 10)["custo_por_hectare"] is None
        assert calcular_custo_safra(1000.0, 10, 0)["custo_por_tonelada"] is None
        assert calcular_custo_safra(1000.0, 10, None)["custo_por_tonelada"] is None

    def test_arredonda_para_duas_casas(self):
        r = calcular_custo_safra(1000.0, 3.0, 7.0)
        assert r["custo_por_hectare"] == 333.33
        assert r["custo_por_tonelada"] == 142.86


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
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


class TestCadastroSafra:
    def _payload(self, **over):
        base = {
            "nome": "Silagem Milho 2026",
            "centro_custo": "Agricultura",
            "data_inicio": "2026-01-01",
            "data_fim": "2026-07-31",
            "hectares": 252.0,
            "toneladas_produzidas": 15510.52,
            "observacao": "252 ha, 61,5 ton/ha",
        }
        base.update(over)
        return base

    def test_cria_e_lista_safra(self, client):
        c, _ = client
        r = c.post("/safras/", json=self._payload())
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nome"] == "Silagem Milho 2026"
        assert d["centro_custo"] == "Agricultura"
        assert d["ativo"] is True

        r = c.get("/safras/")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_rejeita_nome_duplicado(self, client):
        c, _ = client
        c.post("/safras/", json=self._payload())
        r = c.post("/safras/", json=self._payload())
        assert r.status_code == 400

    def test_rejeita_data_fim_antes_da_data_inicio(self, client):
        c, _ = client
        r = c.post("/safras/", json=self._payload(data_inicio="2026-07-31", data_fim="2026-01-01"))
        assert r.status_code == 400

    def test_rejeita_hectares_ou_toneladas_nao_positivos(self, client):
        c, _ = client
        assert c.post("/safras/", json=self._payload(hectares=0)).status_code == 400
        assert c.post("/safras/", json=self._payload(toneladas_produzidas=0)).status_code == 400

    def test_atualiza_safra(self, client):
        c, _ = client
        criada = c.post("/safras/", json=self._payload()).json()
        r = c.put(f"/safras/{criada['id']}", json=self._payload(hectares=300.0, ativo=False))
        assert r.status_code == 200
        d = r.json()
        assert d["hectares"] == 300.0
        assert d["ativo"] is False


class TestEndpointCustoSafra:
    def _sessao(self, engine):
        return Session(engine)

    def test_safra_inexistente_da_404(self, client):
        c, _ = client
        r = c.get("/financeiro/custo-safra", params={"safra_id": 999})
        assert r.status_code == 404

    def test_soma_despesas_do_centro_de_custo_e_periodo_da_safra(self, client):
        c, engine = client
        with self._sessao(engine) as session:
            safra = Safra(
                nome="Silagem Milho 2026", centro_custo="Agricultura",
                data_inicio=date(2026, 1, 1), data_fim=date(2026, 7, 31),
                hectares=252.0, toneladas_produzidas=15510.52,
            )
            session.add(safra)
            session.commit()
            session.refresh(safra)
            safra_id = safra.id

            # Dentro do centro de custo e período — conta. Duas contas dentro
            # do mesmo nível 1 (3.01 e 3.02) somam na mesma categoria "3";
            # 5.01 fica em categoria própria — mesmo agrupamento do DRE
            # (nível 1 do código, ver GET /financeiro/dre).
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00001", tipo="despesa", valor_total=100_000.0,
                data_competencia=date(2026, 3, 10), centro_custo="Agricultura",
                codigo_conta="3.01", descricao="Operações de colheita",
            ))
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00002", tipo="despesa", valor_total=50_000.0,
                data_competencia=date(2026, 4, 10), centro_custo="Agricultura",
                codigo_conta="3.02", descricao="Insumos de lavoura",
            ))
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00003", tipo="despesa", valor_total=30_000.0,
                data_competencia=date(2026, 5, 10), centro_custo="Agricultura",
                codigo_conta="5.01", descricao="Arrendamento",
            ))
            # Fora do centro de custo — não conta.
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00004", tipo="despesa", valor_total=999.0,
                data_competencia=date(2026, 3, 10), centro_custo="Pecuária Leiteira",
                codigo_conta="3.01",
            ))
            # Fora do período da safra — não conta.
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00005", tipo="despesa", valor_total=888.0,
                data_competencia=date(2027, 1, 10), centro_custo="Agricultura",
                codigo_conta="3.01",
            ))
            # Receita — nunca conta.
            session.add(ContaGerencial(
                numero_lancamento="LC-2026-00006", tipo="receita", valor_total=777.0,
                data_competencia=date(2026, 3, 10), centro_custo="Agricultura",
                codigo_conta="4.01",
            ))
            session.commit()

        r = c.get("/financeiro/custo-safra", params={"safra_id": safra_id})
        assert r.status_code == 200
        d = r.json()
        assert d["despesas_total"] == 180_000.0
        assert d["hectares"] == 252.0
        assert d["toneladas_produzidas"] == 15510.52
        assert round(d["custo_por_hectare"], 2) == round(180_000.0 / 252.0, 2)
        assert round(d["custo_por_tonelada"], 2) == round(180_000.0 / 15510.52, 2)

        categorias = {p["codigo"]: p["valor"] for p in d["por_categoria"]}
        assert categorias == {"3": 150_000.0, "5": 30_000.0}
