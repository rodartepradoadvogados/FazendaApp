"""
Testes do lançamento de controle leiteiro (por vaca ou em lote, de uma vez).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ControleLeiteiro


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
        with Session(engine) as s:
            s.add(Animal(numero="101", grupo_primario="01 - Alta", raca="Girolando", del_dias=50, ativo=True))
            s.add(Animal(numero="102", grupo_primario="01 - Alta", raca="Holandês", del_dias=80, ativo=True))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestCriarControles:
    def test_lanca_uma_vaca(self, client):
        r = client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, 10.0]}],
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 1

    def test_lanca_lote_inteiro_de_uma_vez(self, client):
        r = client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [
                {"numero_matriz": "101", "ordenhas": [12.5, 10.0]},
                {"numero_matriz": "102", "ordenhas": [9.0, 8.0]},
            ],
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 2

    def test_soma_as_ordenhas_e_herda_del_e_raca(self, client):
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, 10.0]}],
        })
        r = client.get("/producao/controles")
        registro = next(c for c in r.json()["controles"] if c["numero"] == "101")
        assert registro["producao_kg"] == 22.5
        assert registro["del"] == 50

    def test_pula_entradas_sem_nenhuma_ordenha(self, client):
        r = client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [
                {"numero_matriz": "101", "ordenhas": [12.5, 10.0]},
                {"numero_matriz": "102", "ordenhas": [0, 0]},
            ],
        })
        assert r.json()["criados"] == 1

    def test_persiste_ordenhas_individuais_e_grupo_atual(self, client):
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, 10.0]}],
        })
        r = client.get("/producao/controles")
        registro = next(c for c in r.json()["controles"] if c["numero"] == "101")
        assert registro["ordenha1_kg"] == 12.5
        assert registro["ordenha2_kg"] == 10.0
        assert registro["ordenha3_kg"] is None
        assert registro["grupo_primario"] == "01 - Alta"

    def test_reenviar_o_mesmo_animal_no_mesmo_dia_atualiza_em_vez_de_duplicar(self, client):
        """#68/#72 — reenvio (duplo clique, funcionário achando que não
        salvou) não pode duplicar a produção do dia; upsert por
        (numero_matriz, data_controle) em vez de inserir de novo."""
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, 10.0]}],
        })
        r2 = client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [15.0, 11.0]}],
        })
        assert r2.status_code == 200
        assert r2.json()["criados"] == 1

        r = client.get("/producao/controles")
        registros_101 = [c for c in r.json()["controles"] if c["numero"] == "101"]
        assert len(registros_101) == 1
        assert registros_101[0]["producao_kg"] == 26.0

    def test_persiste_terceira_ordenha(self, client):
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "102", "ordenhas": [8.0, 7.0, 3.0]}],
        })
        r = client.get("/producao/controles")
        registro = next(c for c in r.json()["controles"] if c["numero"] == "102")
        assert registro["ordenha3_kg"] == 3.0

    def test_ordenha_nao_lancada_fica_nula_e_nao_vira_zero(self, client):
        # Regressão: uma ordenha em branco (não lançada) deve ficar None, não
        # 0 — um 0 gravado como se fosse ordenha real puxaria a média de
        # manhã/noite do relatório para baixo silenciosamente.
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, None]}],
        })
        r = client.get("/producao/controles")
        registro = next(c for c in r.json()["controles"] if c["numero"] == "101")
        assert registro["ordenha1_kg"] == 12.5
        assert registro["ordenha2_kg"] is None
        assert registro["producao_kg"] == 12.5
