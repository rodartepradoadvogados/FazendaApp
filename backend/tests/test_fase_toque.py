"""
Fase do ciclo de diagnóstico (a tocar / a reconfirmar / reconfirmada) e o prazo AINDA NÃO — rules/fase_toque.py —
e a fiação nos cards configuráveis (`/reproducao/agenda-reprodutiva/card` e `/cards`): front envia → back grava →
back devolve (o Pydantic descarta campo desconhecido sem erro, então o round-trip é teste obrigatório).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ParametroFazenda, Servico
from fazenda.rules.estado_reprodutivo import GESTANTE, INSEMINADA, PEV
from fazenda.rules.fase_toque import A_RECONFIRMAR, A_TOCAR, RECONFIRMADA, classificar_fase

HOJE = date(2026, 10, 17)


def _fase(estado, dias_ia, eh_vaca=False, toque=30, reconf=30, **diag):
    return classificar_fase({"estado": estado, "dias_desde_servico": dias_ia, **diag},
                            eh_vaca=eh_vaca, dias_toque=toque, dias_reconfirmacao=reconf)


class TestRegra:
    def test_inseminada_sem_diagnostico_e_a_tocar(self):
        r = _fase(INSEMINADA, 35)
        assert r["fase"] == A_TOCAR and r["ainda_nao"] is False and r["dias_para_prazo"] is None

    def test_ainda_nao_conta_os_dias_que_faltam_para_o_toque(self):
        r = _fase(INSEMINADA, 18)
        assert r["fase"] == A_TOCAR and r["ainda_nao"] is True and r["dias_para_prazo"] == 12 and r["prazo_tipo"] == "toque"

    def test_no_dia_exato_do_prazo_ja_esta_no_prazo(self):
        assert _fase(INSEMINADA, 30)["ainda_nao"] is False

    def test_prazo_usa_o_parametro_da_fazenda_e_nao_um_numero_fixo(self):
        assert _fase(INSEMINADA, 32, toque=35)["dias_para_prazo"] == 3
        assert _fase(INSEMINADA, 32, toque=28)["ainda_nao"] is False

    def test_toque_indefinido_volta_para_a_tocar(self):
        # o classificador de estado já devolve INSEMINADA para INDEFINIDO
        r = _fase(INSEMINADA, 40, diagnostico="INDEFINIDO", retoque=True)
        assert r["fase"] == A_TOCAR

    def test_positivo_marcado_para_retoque_e_a_reconfirmar(self):
        r = _fase(GESTANTE, 41, eh_vaca=False, diagnostico="POSITIVO", retoque=True)
        assert r["fase"] == A_RECONFIRMAR and r["ainda_nao"] is True and r["dias_para_prazo"] == 19
        assert r["prazo_tipo"] == "reconfirmacao"

    def test_prazo_de_reconfirmacao_soma_os_dois_parametros(self):
        assert _fase(GESTANTE, 58, diagnostico="POSITIVO", retoque=True, toque=30, reconf=35)["dias_para_prazo"] == 7
        assert _fase(GESTANTE, 60, diagnostico="POSITIVO", retoque=True)["ainda_nao"] is False

    def test_reconfirmacao_positiva_e_reconfirmada(self):
        r = _fase(GESTANTE, 90, eh_vaca=True, diagnostico="POSITIVO", diagnostico_reconfirmacao="POSITIVO", retoque=False)
        assert r["fase"] == RECONFIRMADA and r["ainda_nao"] is False

    def test_reconfirmada_direto_no_lancamento_nao_volta_para_reconfirmar(self):
        assert _fase(GESTANTE, 70, eh_vaca=True, diagnostico="POSITIVO", retoque=False)["fase"] == RECONFIRMADA

    def test_vaca_importada_sem_marca_de_retoque_ainda_precisa_reconfirmar(self):
        assert _fase(GESTANTE, 70, eh_vaca=True, diagnostico="POSITIVO", retoque=None)["fase"] == A_RECONFIRMAR

    def test_novilha_importada_sem_marca_dispensa_o_segundo_toque(self):
        assert _fase(GESTANTE, 70, eh_vaca=False, diagnostico="POSITIVO", retoque=None)["fase"] == RECONFIRMADA

    def test_marca_explicita_de_retoque_vale_tambem_para_novilha(self):
        assert _fase(GESTANTE, 45, eh_vaca=False, diagnostico="POSITIVO", retoque=True)["fase"] == A_RECONFIRMAR

    def test_estado_sem_ciclo_de_diagnostico_nao_tem_fase(self):
        r = _fase(PEV, None)
        assert r["fase"] is None and r["ainda_nao"] is False

    def test_sem_data_de_servico_nao_inventa_prazo(self):
        r = _fase(INSEMINADA, None)
        assert r["fase"] == A_TOCAR and r["ainda_nao"] is False and r["dias_para_prazo"] is None


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _animal(engine, numero, categoria="Novilha"):
    with Session(engine) as s:
        s.add(Animal(numero=numero, categoria_abrev=categoria, sexo="F", ativo=True, grupo_primario="13 - Novilhas Novas"))
        s.commit()


def _servico(engine, numero, dias_atras, **kw):
    with Session(engine) as s:
        s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), **kw))
        s.commit()


def _param(engine, chave, valor):
    with Session(engine) as s:
        s.add(ParametroFazenda(chave=chave, fazenda_id=None, grupo="manejo", label=chave, valor=str(valor), tipo="int"))
        s.commit()


def _um(c, **body):
    return c.post("/reproducao/agenda-reprodutiva/card", params={"data": HOJE.isoformat()}, json=body)


class TestEndpointCard:
    def test_item_devolve_diagnostico_fase_e_prazo(self, client):
        c, engine = client
        _animal(engine, "2341")
        _servico(engine, "2341", 18)  # sem diagnóstico, 18 dias: a tocar, ainda não
        _animal(engine, "460")
        _servico(engine, "460", 41, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=9), retoque=True)
        r1 = _um(c, situacao="inseminada")
        assert r1.status_code == 200
        corpo = r1.json()
        assert corpo["parametros"] == {"dias_toque": 30, "dias_reconfirmacao": 30}
        it = corpo["itens"][0]
        assert it["numero_matriz"] == "2341"
        assert (it["fase"], it["ainda_nao"], it["dias_para_prazo"], it["prazo_tipo"]) == ("a_tocar", True, 12, "toque")
        assert it["diagnostico"] is None and it["data_diagnostico"] is None
        r2 = _um(c, situacao="gestante").json()["itens"][0]
        assert r2["numero_matriz"] == "460" and r2["fase"] == "a_reconfirmar"
        assert r2["diagnostico"] == "POSITIVO" and r2["data_diagnostico"] == (HOJE - timedelta(days=9)).isoformat()
        assert r2["retoque"] is True and r2["dias_para_prazo"] == 19

    def test_parametros_da_fazenda_mudam_o_ainda_nao(self, client):
        c, engine = client
        _param(engine, "dias_toque", 35)
        _animal(engine, "03")
        _servico(engine, "03", 32)
        it = _um(c, situacao="inseminada").json()["itens"][0]
        assert it["ainda_nao"] is True and it["dias_para_prazo"] == 3

    def test_gestante_reconfirmada_traz_a_data_do_retoque(self, client):
        c, engine = client
        _animal(engine, "1830", "Vaca")
        _servico(engine, "1830", 140, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=100),
                 diagnostico_reconfirmacao="POSITIVO", data_reconfirmacao=HOJE - timedelta(days=70), retoque=False)
        it = _um(c, situacao="gestante").json()["itens"][0]
        assert it["fase"] == "reconfirmada" and it["data_reconfirmacao"] == (HOJE - timedelta(days=70)).isoformat()
        assert it["diagnostico_reconfirmacao"] == "POSITIVO"


class TestEndpointEmLote:
    def test_lote_devolve_o_mesmo_que_cada_card_separado(self, client):
        c, engine = client
        _animal(engine, "2341")
        _servico(engine, "2341", 18)
        _animal(engine, "460")
        _servico(engine, "460", 41, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=9), retoque=True)
        cards = [
            {"id": "ins", "config": {"situacao": "inseminada"}},
            {"id": "ges", "config": {"situacao": "gestante", "categoria": "novilha"}},
            {"id": "pev", "config": {"situacao": "pev"}},
        ]
        r = c.post("/reproducao/agenda-reprodutiva/cards", params={"data": HOJE.isoformat()}, json={"cards": cards})
        assert r.status_code == 200, r.text
        lote = r.json()
        assert set(lote["resultados"]) == {"ins", "ges", "pev"}
        assert lote["parametros"] == {"dias_toque": 30, "dias_reconfirmacao": 30}
        for card in cards:
            avulso = _um(c, **card["config"]).json()
            assert lote["resultados"][card["id"]]["itens"] == avulso["itens"]
            assert lote["resultados"][card["id"]]["total"] == avulso["total"]

    def test_lote_valida_cada_card(self, client):
        c, _ = client
        r = c.post("/reproducao/agenda-reprodutiva/cards", json={"cards": [{"id": "x", "config": {"situacao": "inexistente"}}]})
        assert r.status_code == 422

    def test_lote_limita_a_quantidade_de_cards(self, client):
        c, _ = client
        cards = [{"id": str(i), "config": {"situacao": "pev"}} for i in range(41)]
        assert c.post("/reproducao/agenda-reprodutiva/cards", json={"cards": cards}).status_code == 422
