"""
Cadastro manual de patrimônio (substitui o CSV), patrimônio não depreciável
com valor de mercado agendável, vínculo FK com lançamento financeiro e o
acesso admin-only da aba — ver fazenda/api/routers/financeiro.py e
fazenda/rules/patrimonio.py.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial, Patrimonio


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin-teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    import fazenda.api.routers.financeiro as financeiro_mod
    monkeypatch.setattr(financeiro_mod, "enviar_arquivo", lambda *a, **k: None)
    monkeypatch.setattr(financeiro_mod, "baixar_arquivo", lambda *a, **k: b"")
    monkeypatch.setattr(financeiro_mod, "excluir_arquivo", lambda *a, **k: None)

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestCadastroManualPatrimonio:
    def test_cria_patrimonio_depreciavel(self, client):
        c, _ = client
        r = c.post("/financeiro/patrimonio", json={
            "nome": "Trator Massey", "tipo": "Máquinas", "data_imobilizacao": "2024-01-10",
            "metodo_depreciacao": "Linear", "vida_util": "10 Anos", "valor_residual": 5000, "valor_total": 150000,
        })
        assert r.status_code == 201
        assert r.json()["depreciavel"] is True
        assert r.json()["valor_mercado_atual"] is None

    def test_cria_patrimonio_nao_depreciavel_usa_valor_total_como_mercado_inicial(self, client):
        c, _ = client
        r = c.post("/financeiro/patrimonio", json={
            "nome": "Fazenda Sede", "tipo": "Terra", "valor_total": 2000000, "depreciavel": False,
        })
        assert r.status_code == 201
        assert r.json()["valor_mercado_atual"] == 2000000

    def test_edita_patrimonio(self, client):
        c, _ = client
        item_id = c.post("/financeiro/patrimonio", json={"nome": "Ordenhadeira", "valor_total": 30000}).json()["id"]
        r = c.put(f"/financeiro/patrimonio/{item_id}", json={"nome": "Ordenhadeira nova", "valor_total": 32000})
        assert r.status_code == 200
        assert r.json()["nome"] == "Ordenhadeira nova"

    def test_sem_nome_da_erro(self, client):
        c, _ = client
        r = c.post("/financeiro/patrimonio", json={"nome": "   ", "valor_total": 100})
        assert r.status_code == 400


class TestValorMercado:
    def _criar_nao_depreciavel(self, c) -> int:
        return c.post("/financeiro/patrimonio", json={
            "nome": "Terreno", "valor_total": 500000, "depreciavel": False,
        }).json()["id"]

    def test_registra_novo_valor_de_mercado(self, client):
        c, _ = client
        item_id = self._criar_nao_depreciavel(c)
        r = c.put(f"/financeiro/patrimonio/{item_id}/valor-mercado", json={"valor_mercado_atual": 550000, "data": "2026-08-01"})
        assert r.status_code == 200
        assert r.json()["valor_mercado_atual"] == 550000
        assert r.json()["data_ultima_atualizacao_valor_mercado"] == "2026-08-01"

    def test_bloqueado_para_item_depreciavel(self, client):
        c, _ = client
        item_id = c.post("/financeiro/patrimonio", json={"nome": "Trator", "valor_total": 100000}).json()["id"]
        r = c.put(f"/financeiro/patrimonio/{item_id}/valor-mercado", json={"valor_mercado_atual": 90000})
        assert r.status_code == 400

    def test_listar_patrimonio_nao_deprecia_item_marcado(self, client):
        c, _ = client
        item_id = self._criar_nao_depreciavel(c)
        itens = c.get("/financeiro/patrimonio").json()["itens"]
        item = next(i for i in itens if i["id"] == item_id)
        assert item["valor_atual"] == 500000
        assert item["inconsistencia"] is None  # não exige vida_util/data_imobilizacao

    def test_agenda_pendencia_valor_mercado_vencida(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Patrimonio(
                nome="Terreno antigo", valor_total=100000, depreciavel=False,
                data_ultima_atualizacao_valor_mercado=date(2020, 1, 1),
                atualizacao_valor_mercado_frequencia_meses=12,
            ))
            s.commit()
        eventos = c.get("/agenda/", params={"data": "2026-08-04"}).json()["eventos"]
        assert any(e.get("tipo") == "patrimonio_valor_mercado" for e in eventos)

    def test_agenda_sem_pendencia_quando_frequencia_e_nunca(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Patrimonio(
                nome="Terreno sem pendencia", valor_total=100000, depreciavel=False,
                data_ultima_atualizacao_valor_mercado=date(2020, 1, 1),
                atualizacao_valor_mercado_frequencia_meses=0,
            ))
            s.commit()
        eventos = c.get("/agenda/", params={"data": "2026-08-04"}).json()["eventos"]
        assert not any(e.get("tipo") == "patrimonio_valor_mercado" for e in eventos)

    def test_pendencia_nao_pode_ser_dispensada_direto(self, client):
        c, engine = client
        with Session(engine) as s:
            item = Patrimonio(
                nome="Terreno", valor_total=100000, depreciavel=False,
                data_ultima_atualizacao_valor_mercado=date(2020, 1, 1),
                atualizacao_valor_mercado_frequencia_meses=12,
            )
            s.add(item); s.commit(); s.refresh(item)
            item_id = item.id
        r = c.post("/agenda/realizados", json={"evento_id": f"patrimonio_valor_mercado_{item_id}"})
        assert r.status_code == 400


class TestVinculoLancamentoPatrimonio:
    def test_vincula_lancamento_a_patrimonio_existente(self, client):
        c, _ = client
        item_id = c.post("/financeiro/patrimonio", json={"nome": "Trator", "valor_total": 100000}).json()["id"]
        numero = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "itens": [{"produto": "Trator novo", "valor_total": 100000.0}],
        }).json()["numero_lancamento"]
        r = c.put(f"/financeiro/lancamentos/{numero}/patrimonio", json={"patrimonio_id": item_id})
        assert r.status_code == 200
        lanc = next(l for l in c.get("/financeiro/lancamentos").json()["lancamentos"] if l["numero_lancamento"] == numero)
        assert lanc["patrimonio_id"] == item_id

    def test_desvincula_com_patrimonio_id_nulo(self, client):
        c, _ = client
        item_id = c.post("/financeiro/patrimonio", json={"nome": "Trator", "valor_total": 100000}).json()["id"]
        numero = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "itens": [{"produto": "Trator novo", "valor_total": 100000.0}],
        }).json()["numero_lancamento"]
        c.put(f"/financeiro/lancamentos/{numero}/patrimonio", json={"patrimonio_id": item_id})
        r = c.put(f"/financeiro/lancamentos/{numero}/patrimonio", json={"patrimonio_id": None})
        assert r.status_code == 200
        lanc = next(l for l in c.get("/financeiro/lancamentos").json()["lancamentos"] if l["numero_lancamento"] == numero)
        assert lanc["patrimonio_id"] is None

    def test_criar_patrimonio_junto_com_o_lancamento(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "itens": [{"produto": "Trator novo", "valor_total": 120000.0}],
            "criar_patrimonio": {"nome": "Trator novo", "valor_total": 120000, "tipo": "Máquinas"},
        })
        assert r.status_code == 201
        numero = r.json()["numero_lancamento"]
        lanc = next(l for l in c.get("/financeiro/lancamentos").json()["lancamentos"] if l["numero_lancamento"] == numero)
        assert lanc["patrimonio_id"] is not None
        itens_patrimonio = c.get("/financeiro/patrimonio").json()["itens"]
        assert any(i["id"] == lanc["patrimonio_id"] and i["nome"] == "Trator novo" for i in itens_patrimonio)

    def test_patrimonio_inexistente_da_404(self, client):
        c, _ = client
        numero = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "itens": [{"produto": "Insumo", "valor_total": 500.0}],
        }).json()["numero_lancamento"]
        r = c.put(f"/financeiro/lancamentos/{numero}/patrimonio", json={"patrimonio_id": 9999})
        assert r.status_code == 404


class TestAcessoAdminOnly:
    """A aba Patrimônio (dentro de Financeiro) é só para administradores da
    fazenda — operador comum com módulo financeiro continua acessando o
    resto do Financeiro normalmente, só fica de fora de Patrimônio."""

    @pytest.fixture
    def client_operador(self, monkeypatch):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        from fazenda.auth import get_current_user

        class _FakeOperador:
            id = 2
            papel = "operador"
            ativo = True
            username = "operador-teste"
            permissoes = "financeiro"

        main.app.dependency_overrides[database.get_session] = _get_session_override
        main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()

        with TestClient(main.app) as c:
            yield c

        main.app.dependency_overrides.clear()

    def test_operador_bloqueado_de_listar_patrimonio(self, client_operador):
        assert client_operador.get("/financeiro/patrimonio").status_code == 403

    def test_operador_bloqueado_de_criar_patrimonio(self, client_operador):
        r = client_operador.post("/financeiro/patrimonio", json={"nome": "Trator", "valor_total": 1000})
        assert r.status_code == 403

    def test_operador_continua_acessando_lancamentos_normais(self, client_operador):
        assert client_operador.get("/financeiro/opcoes").status_code == 200
