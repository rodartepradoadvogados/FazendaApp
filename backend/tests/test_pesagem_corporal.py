"""
Testes de pesagem corporal (peso vivo) — lançamento e relatório de GMD/GPD.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal


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
            s.add(Animal(numero="301", grupo_primario="04 - Novilhas", del_dias=None, idade_meses=12, ativo=True))
            s.add(Animal(numero="302", grupo_primario="04 - Novilhas", del_dias=None, idade_meses=14, ativo=True))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestCriarPesagens:
    def test_lanca_uma_vaca(self, client):
        r = client.post("/producao/pesagens", json={
            "data_pesagem": "2026-01-01",
            "entradas": [{"numero_matriz": "301", "peso_kg": 300}],
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 1

    def test_lanca_lote_inteiro(self, client):
        r = client.post("/producao/pesagens", json={
            "data_pesagem": "2026-01-01",
            "entradas": [
                {"numero_matriz": "301", "peso_kg": 300},
                {"numero_matriz": "302", "peso_kg": 320},
            ],
        })
        assert r.json()["criados"] == 2

    def test_pula_entradas_sem_peso(self, client):
        r = client.post("/producao/pesagens", json={
            "data_pesagem": "2026-01-01",
            "entradas": [{"numero_matriz": "301", "peso_kg": 0}],
        })
        assert r.json()["criados"] == 0


class TestRelatorioPesagens:
    def _lancar(self, client, data, numero, peso):
        client.post("/producao/pesagens", json={"data_pesagem": data, "entradas": [{"numero_matriz": numero, "peso_kg": peso}]})

    def test_gmd_e_gpd_com_pesagens_regulares(self, client):
        # 301: 300kg -> 320kg -> 340kg, 20 dias entre cada pesagem (1kg/dia constante)
        self._lancar(client, "2026-01-01", "301", 300)
        self._lancar(client, "2026-01-21", "301", 320)
        self._lancar(client, "2026-02-10", "301", 340)

        r = client.get("/producao/pesagens/relatorio", params={"numero_matriz": "301"})
        assert r.status_code == 200
        linha = r.json()["linhas"][0]
        assert linha["primeira_peso"] == 300
        assert linha["ultima_peso"] == 340
        assert linha["gmd_kg_dia"] == 1.0
        assert linha["gpd_kg_dia"] == 1.0
        assert linha["num_pesagens"] == 3

    def test_filtra_por_periodo(self, client):
        self._lancar(client, "2026-01-01", "301", 300)
        self._lancar(client, "2026-01-21", "301", 320)
        self._lancar(client, "2026-02-10", "301", 340)

        r = client.get("/producao/pesagens/relatorio", params={
            "numero_matriz": "301", "data_inicio": "2026-01-15", "data_fim": "2026-02-28",
        })
        linha = r.json()["linhas"][0]
        assert linha["num_pesagens"] == 2
        assert linha["primeira_peso"] == 320

    def test_filtra_por_lote(self, client):
        self._lancar(client, "2026-01-01", "301", 300)
        self._lancar(client, "2026-01-21", "301", 320)
        self._lancar(client, "2026-01-01", "302", 310)
        self._lancar(client, "2026-01-21", "302", 330)

        r = client.get("/producao/pesagens/relatorio", params={"grupo": "04 - Novilhas"})
        assert r.json()["total"] == 2

    def test_todos_os_animais_sem_filtro(self, client):
        self._lancar(client, "2026-01-01", "301", 300)
        self._lancar(client, "2026-01-01", "302", 310)
        r = client.get("/producao/pesagens/relatorio")
        assert r.json()["total"] == 2

    def test_uma_unica_pesagem_nao_calcula_gmd(self, client):
        self._lancar(client, "2026-01-01", "301", 300)
        r = client.get("/producao/pesagens/relatorio", params={"numero_matriz": "301"})
        linha = r.json()["linhas"][0]
        assert linha["gmd_kg_dia"] is None
        assert linha["gpd_kg_dia"] is None
