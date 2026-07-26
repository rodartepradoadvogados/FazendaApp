"""
Testes dos novos endpoints de histórico usados pelas sub-sub-abas de
Reprodução: partos, secagens (listas achatadas) e perda de prenhez (registro
manual com motivo).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Parto, Secagem, Servico


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


class TestListarPartosHistorico:
    def test_lista_partos_achatados(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="501", sit_rep="Ins.", ativo=True))
            s.add(Parto(numero_matriz="501", data_parto=date(2026, 3, 10), ordem_parto=2, tipo_parto="Normal"))
            s.commit()
        r = c.get("/reproducao/partos")
        assert r.status_code == 200
        dados = r.json()
        assert dados["total"] == 1
        assert dados["partos"][0]["numero"] == "501"
        assert dados["partos"][0]["ordem_parto"] == 2
        assert dados["partos"][0]["ano"] == 2026
        assert dados["partos"][0]["mes"] == "2026-03"


class TestListarSecagensHistorico:
    def test_lista_secagens_achatadas(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="502", sit_rep="Ins.", ativo=True))
            s.add(Secagem(numero_matriz="502", data_secagem=date(2026, 4, 1), motivo="rotina"))
            s.commit()
        r = c.get("/reproducao/secagens")
        assert r.status_code == 200
        dados = r.json()
        assert dados["total"] == 1
        assert dados["secagens"][0]["numero"] == "502"
        assert dados["secagens"][0]["motivo"] == "rotina"


class TestRegistrarPerdaPrenhez:
    def test_registra_perda_com_motivo(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="503", sit_rep="Ins.", ativo=True))
            s.add(Servico(numero_matriz="503", data_servico=date(2026, 1, 5), diagnostico="POSITIVO"))
            s.commit()
        r = c.post("/reproducao/perda-prenhez", json={
            "numero_matriz": "503", "data_perda_prenhez": "2026-03-01", "motivo": "aborto",
        })
        assert r.status_code == 200
        dados = r.json()
        assert dados["data_perda_prenhez"] == "2026-03-01"
        assert dados["motivo_perda_prenhez"] == "aborto"

    def test_rejeita_motivo_invalido(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="504", sit_rep="Ins.", ativo=True))
            s.add(Servico(numero_matriz="504", data_servico=date(2026, 1, 5)))
            s.commit()
        r = c.post("/reproducao/perda-prenhez", json={
            "numero_matriz": "504", "data_perda_prenhez": "2026-03-01", "motivo": "desconhecido",
        })
        assert r.status_code == 400

    def test_rejeita_matriz_sem_servico(self, client):
        c, engine = client
        r = c.post("/reproducao/perda-prenhez", json={
            "numero_matriz": "999", "data_perda_prenhez": "2026-03-01", "motivo": "outros",
        })
        assert r.status_code == 404

    def test_aparece_no_historico_de_servicos_com_motivo(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="505", sit_rep="Ins.", ativo=True))
            s.add(Servico(numero_matriz="505", data_servico=date(2026, 1, 5), diagnostico="POSITIVO"))
            s.commit()
        c.post("/reproducao/perda-prenhez", json={
            "numero_matriz": "505", "data_perda_prenhez": "2026-03-01", "motivo": "natimorto",
        })
        r = c.get("/reproducao/servicos")
        assert r.status_code == 200
        reg = next(x for x in r.json()["servicos"] if x["numero"] == "505")
        assert reg["perda"] is True
        assert reg["motivo_perda"] == "natimorto"
        assert reg["data_perda"] == "2026-03-01"


class TestDataD0DoServicoIatf:
    """GET /reproducao/servicos deve trazer o D0 real do protocolo IATF que
    originou o serviço (usado pela tela para agrupar "ciclo" corretamente —
    ver _mapa_data_d0_por_servico). Sem isso, a tela ancorava o ciclo na
    data do serviço mais recente do filtro, não no D0 verdadeiro."""

    def test_servico_de_iatf_traz_o_d0_do_protocolo(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="700", sit_rep="Vaz. apt.", ativo=True))
            s.commit()
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": "2026-06-12", "protocolo": "IATF 12/06 a 23/06",
        })
        # D11 = D0 + 11 dias — a inseminação em si é lançada à parte, e resolve
        # a ProtocoloIatfAplicacao (dia 11) em aberto automaticamente pelo nome
        # do protocolo (mesma regra de registrar_servico).
        r = c.post("/reproducao/servico", json={
            "numero_matriz": "700", "data_servico": "2026-06-23", "tipo_servico": "IA",
            "protocolo": "IATF 12/06 a 23/06",
        })
        assert r.status_code == 200

        servicos = c.get("/reproducao/servicos").json()["servicos"]
        reg = next(x for x in servicos if x["numero"] == "700")
        assert reg["data_d0"] == "2026-06-12"

    def test_servico_sem_protocolo_nao_tem_d0(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="701", sit_rep="Vaz. apt.", ativo=True))
            s.commit()
        c.post("/reproducao/servico", json={
            "numero_matriz": "701", "data_servico": "2026-06-23", "tipo_servico": "Monta natural",
        })
        servicos = c.get("/reproducao/servicos").json()["servicos"]
        reg = next(x for x in servicos if x["numero"] == "701")
        assert reg["data_d0"] is None
