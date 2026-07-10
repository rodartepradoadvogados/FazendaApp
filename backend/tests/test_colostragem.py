"""
Testes de colostragem/teste de sangue (IgG) da cria e do relatório sanitário
de bezerras (Sanidade).
"""
from __future__ import annotations

from datetime import date, timedelta

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
        yield c, engine

    main.app.dependency_overrides.clear()


class TestRegistrarColostragem:
    def test_animal_inexistente_404(self, client):
        c, engine = client
        r = c.post("/sanidade/colostragem", json={"numero_animal": "999"})
        assert r.status_code == 404

    def test_registra_e_atualiza(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="700", data_nasc=date(2026, 6, 1), sexo="F"))
            s.commit()

        r = c.post("/sanidade/colostragem", json={
            "numero_animal": "700", "tomou_colostro": True, "litros_colostro": 3.0,
            "brix_colostro": 22.0, "data_colostro": "2026-06-01",
        })
        assert r.status_code == 200
        assert r.json()["brix_colostro"] == 22.0

        r2 = c.post("/sanidade/colostragem", json={
            "numero_animal": "700", "brix_soro": 8.5, "data_teste_sangue": "2026-06-02",
        })
        assert r2.status_code == 200
        assert r2.json()["brix_soro"] == 8.5
        # Não deve criar um segundo registro para o mesmo animal.
        assert r2.json()["id"] == r.json()["id"]


class TestRelatorioBezerras:
    def _seed(self, session):
        hoje = date.today()
        session.add(Animal(numero="701", data_nasc=hoje - timedelta(days=60), sexo="F", grupo_primario="Lote 1"))
        session.add(Animal(numero="702", data_nasc=hoje - timedelta(days=400), sexo="F", grupo_primario="Lote 2"))
        session.commit()

    def test_classifica_colostro_e_soro(self, client):
        c, engine = client
        with Session(engine) as s:
            self._seed(s)
        c.post("/sanidade/colostragem", json={"numero_animal": "701", "brix_colostro": 30.0, "brix_soro": 7.5})

        r = c.get("/sanidade/relatorio-bezerras")
        assert r.status_code == 200
        linha = next(l for l in r.json() if l["numero"] == "701")
        assert linha["classe_colostro"] == "ouro"
        assert linha["classe_soro"] == "falha"

    def test_filtro_faixa_etaria(self, client):
        c, engine = client
        with Session(engine) as s:
            self._seed(s)

        ate_12 = c.get("/sanidade/relatorio-bezerras", params={"faixa_etaria": "ate_12"}).json()
        assert {l["numero"] for l in ate_12} == {"701"}

        acima_12 = c.get("/sanidade/relatorio-bezerras", params={"faixa_etaria": "acima_12"}).json()
        assert {l["numero"] for l in acima_12} == {"702"}

    def test_filtro_por_lote(self, client):
        c, engine = client
        with Session(engine) as s:
            self._seed(s)
        r = c.get("/sanidade/relatorio-bezerras", params={"lote": "Lote 2"})
        assert {l["numero"] for l in r.json()} == {"702"}

    def test_filtro_por_selecao_de_animais(self, client):
        c, engine = client
        with Session(engine) as s:
            self._seed(s)
        r = c.get("/sanidade/relatorio-bezerras", params={"numeros": ["701", "702"]})
        assert {l["numero"] for l in r.json()} == {"701", "702"}

    def test_animal_sem_registro_aparece_sem_classificacao(self, client):
        c, engine = client
        with Session(engine) as s:
            self._seed(s)
        r = c.get("/sanidade/relatorio-bezerras", params={"numero": "702"})
        linha = r.json()[0]
        assert linha["classe_colostro"] is None
        assert linha["classe_soro"] is None
