"""
Manutenção preventiva de patrimônio (plano opcional por item, só por
periodicidade de data — ver rules/patrimonio.py):
- cadastro/edição do plano (frequência + última/próxima manutenção);
- alerta na Agenda quando a próxima manutenção vence (ou está próxima);
- registro de manutenção paga/realizada, com o lançamento em Contas a Pagar
  gerado automaticamente (mesmo padrão de Férias/13º) e recálculo da próxima
  data a partir da frequência cadastrada.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, ManutencaoPatrimonio, Patrimonio
from fazenda.rules.patrimonio import somar_meses, status_manutencao

HOJE = date.today()


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


def _criar_patrimonio(engine, **overrides) -> int:
    with Session(engine) as s:
        item = Patrimonio(nome="Trator MF 265", tipo="Máquina", valor_total=180000.0, **overrides)
        s.add(item)
        s.commit()
        s.refresh(item)
        return item.id


# ---------------------------------------------------------------------------
# Funções puras (rules/patrimonio.py)
# ---------------------------------------------------------------------------
def test_somar_meses_ajusta_dia_para_mes_mais_curto():
    assert somar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert somar_meses(date(2026, 7, 15), 6) == date(2027, 1, 15)


def test_status_manutencao_sem_plano_fica_none():
    assert status_manutencao({"data_proxima_manutencao": None}) == {
        "situacao_manutencao": None, "dias_para_manutencao": None,
    }


def test_status_manutencao_vencida_proxima_e_ok():
    hoje = date(2026, 7, 20)
    vencida = status_manutencao({"data_proxima_manutencao": hoje - timedelta(days=1)}, hoje)
    proxima = status_manutencao({"data_proxima_manutencao": hoje + timedelta(days=10)}, hoje)
    ok = status_manutencao({"data_proxima_manutencao": hoje + timedelta(days=60)}, hoje)
    assert vencida["situacao_manutencao"] == "vencida"
    assert proxima["situacao_manutencao"] == "proxima"
    assert ok["situacao_manutencao"] == "ok"


def test_status_manutencao_item_baixado_nunca_alerta():
    hoje = date(2026, 7, 20)
    r = status_manutencao({"data_proxima_manutencao": hoje - timedelta(days=30), "data_baixa": hoje - timedelta(days=1)}, hoje)
    assert r["situacao_manutencao"] is None


# ---------------------------------------------------------------------------
# 1) Cadastro do plano de manutenção
# ---------------------------------------------------------------------------
class TestPlanoManutencao:
    def test_cadastra_plano_calcula_proxima_a_partir_da_frequencia(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine)
        r = c.put(f"/financeiro/patrimonio/{item_id}/manutencao-plano", json={
            "frequencia_manutencao_meses": 6,
            "data_ultima_manutencao": (HOJE - timedelta(days=200)).isoformat(),
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["frequencia_manutencao_meses"] == 6
        assert corpo["data_proxima_manutencao"] == somar_meses(HOJE - timedelta(days=200), 6).isoformat()

    def test_cadastra_plano_com_proxima_manual_nao_recalcula(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine)
        proxima_manual = (HOJE + timedelta(days=45)).isoformat()
        r = c.put(f"/financeiro/patrimonio/{item_id}/manutencao-plano", json={
            "frequencia_manutencao_meses": 3,
            "data_ultima_manutencao": HOJE.isoformat(),
            "data_proxima_manutencao": proxima_manual,
        })
        assert r.status_code == 200, r.text
        assert r.json()["data_proxima_manutencao"] == proxima_manual

    def test_plano_e_opcional_item_sem_plano_nao_aparece_no_get(self, client):
        c, engine = client
        _criar_patrimonio(engine)
        r = c.get("/financeiro/patrimonio")
        assert r.status_code == 200
        item = r.json()["itens"][0]
        assert item["data_proxima_manutencao"] is None
        assert item["situacao_manutencao"] is None

    def test_frequencia_invalida_da_400(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine)
        r = c.put(f"/financeiro/patrimonio/{item_id}/manutencao-plano", json={"frequencia_manutencao_meses": 0})
        assert r.status_code == 400

    def test_item_inexistente_da_404(self, client):
        c, _ = client
        r = c.put("/financeiro/patrimonio/999/manutencao-plano", json={"frequencia_manutencao_meses": 6})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 2) Alerta de Agenda quando a manutenção vence
# ---------------------------------------------------------------------------
class TestAlertaAgenda:
    def _eventos_patrimonio(self, c):
        r = c.get("/agenda/", params={"data": HOJE.isoformat()})
        assert r.status_code == 200, r.text
        return [e for e in r.json()["eventos"] if e.get("tipo") == "patrimonio_manutencao"]

    def test_manutencao_vencida_gera_evento_na_agenda(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine, data_proxima_manutencao=HOJE - timedelta(days=5))
        eventos = self._eventos_patrimonio(c)
        assert len(eventos) == 1
        assert eventos[0]["id"] == f"patrimonio_manutencao_{item_id}"
        assert eventos[0]["situacao_manutencao"] == "vencida"
        assert "VENCIDA" in eventos[0]["descricao"]

    def test_manutencao_proxima_tambem_alerta(self, client):
        c, engine = client
        _criar_patrimonio(engine, data_proxima_manutencao=HOJE + timedelta(days=10))
        eventos = self._eventos_patrimonio(c)
        assert len(eventos) == 1
        assert eventos[0]["situacao_manutencao"] == "proxima"

    def test_manutencao_distante_nao_alerta(self, client):
        c, engine = client
        _criar_patrimonio(engine, data_proxima_manutencao=HOJE + timedelta(days=90))
        assert self._eventos_patrimonio(c) == []

    def test_item_baixado_nao_alerta(self, client):
        c, engine = client
        _criar_patrimonio(engine, data_proxima_manutencao=HOJE - timedelta(days=5), data_baixa=HOJE - timedelta(days=1))
        assert self._eventos_patrimonio(c) == []

    def test_alerta_nao_pode_ser_dispensado_direto(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine, data_proxima_manutencao=HOJE - timedelta(days=5))
        r = c.post("/agenda/realizados", json={"evento_id": f"patrimonio_manutencao_{item_id}"})
        assert r.status_code == 400
        # Continua aparecendo depois da tentativa de dispensa.
        assert len(self._eventos_patrimonio(c)) == 1


# ---------------------------------------------------------------------------
# 3) Registrar manutenção realizada/paga — gera conta a pagar e recalcula a
#    próxima data a partir da frequência.
# ---------------------------------------------------------------------------
class TestRegistrarManutencao:
    def test_registrar_manutencao_paga_gera_conta_a_pagar(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine, frequencia_manutencao_meses=6, data_proxima_manutencao=HOJE - timedelta(days=2))
        r = c.post(f"/financeiro/patrimonio/{item_id}/manutencao", json={
            "data_realizacao": HOJE.isoformat(), "descricao": "Troca de óleo e filtros",
            "fornecedor": "Oficina do Zé", "valor": 850.0, "status": "pago",
            "data_pagamento": HOJE.isoformat(),
        })
        assert r.status_code == 201, r.text
        corpo = r.json()
        numero = corpo["manutencao"]["numero_lancamento_gerado"]
        assert numero is not None

        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()
            assert conta is not None
            assert conta.valor_total == 850.0
            assert conta.valor_pago == 850.0
            assert conta.tipo == "despesa"
            assert conta.origem == "auto"
            assert conta.fornecedor_cliente == "Oficina do Zé"

            registro = s.exec(select(ManutencaoPatrimonio).where(ManutencaoPatrimonio.patrimonio_id == item_id)).first()
            assert registro is not None
            assert registro.numero_lancamento_gerado == numero

        # data_proxima_manutencao recalculada a partir da frequência (6 meses).
        assert corpo["item"]["data_ultima_manutencao"] == HOJE.isoformat()
        assert corpo["item"]["data_proxima_manutencao"] == somar_meses(HOJE, 6).isoformat()

        # E o alerta correspondente sai da Agenda.
        eventos = [e for e in c.get("/agenda/", params={"data": HOJE.isoformat()}).json()["eventos"] if e.get("tipo") == "patrimonio_manutencao"]
        assert eventos == []

    def test_registrar_manutencao_pendente_nao_baixa_a_conta(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine)
        r = c.post(f"/financeiro/patrimonio/{item_id}/manutencao", json={
            "data_realizacao": HOJE.isoformat(), "valor": 500.0, "status": "pendente",
        })
        assert r.status_code == 201, r.text
        numero = r.json()["manutencao"]["numero_lancamento_gerado"]
        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()
            assert conta.valor_pago is None
            assert conta.data_pagamento is None

    def test_registrar_manutencao_sem_frequencia_zera_proxima_data(self, client):
        c, engine = client
        # Plano com próxima data manual, mas sem frequência cadastrada: depois
        # de registrar a manutenção, não há como recalcular sozinho.
        item_id = _criar_patrimonio(engine, data_proxima_manutencao=HOJE - timedelta(days=1))
        r = c.post(f"/financeiro/patrimonio/{item_id}/manutencao", json={
            "data_realizacao": HOJE.isoformat(), "valor": 100.0, "gerar_conta_a_pagar": False,
        })
        assert r.status_code == 201, r.text
        assert r.json()["item"]["data_proxima_manutencao"] is None

    def test_gerar_conta_a_pagar_sem_valor_da_400(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine)
        r = c.post(f"/financeiro/patrimonio/{item_id}/manutencao", json={
            "data_realizacao": HOJE.isoformat(), "gerar_conta_a_pagar": True,
        })
        assert r.status_code == 400

    def test_opt_out_conta_a_pagar_nao_gera_lancamento(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine)
        r = c.post(f"/financeiro/patrimonio/{item_id}/manutencao", json={
            "data_realizacao": HOJE.isoformat(), "gerar_conta_a_pagar": False,
        })
        assert r.status_code == 201, r.text
        assert r.json()["manutencao"]["numero_lancamento_gerado"] is None
        with Session(engine) as s:
            assert s.exec(select(ContaGerencial)).all() == []

    def test_historico_de_manutencoes(self, client):
        c, engine = client
        item_id = _criar_patrimonio(engine)
        c.post(f"/financeiro/patrimonio/{item_id}/manutencao", json={
            "data_realizacao": (HOJE - timedelta(days=200)).isoformat(), "gerar_conta_a_pagar": False,
        })
        c.post(f"/financeiro/patrimonio/{item_id}/manutencao", json={
            "data_realizacao": HOJE.isoformat(), "gerar_conta_a_pagar": False,
        })
        r = c.get(f"/financeiro/patrimonio/{item_id}/manutencoes")
        assert r.status_code == 200, r.text
        assert len(r.json()) == 2

    def test_item_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/financeiro/patrimonio/999/manutencao", json={"data_realizacao": HOJE.isoformat(), "gerar_conta_a_pagar": False})
        assert r.status_code == 404
