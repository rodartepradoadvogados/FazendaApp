"""
Testes do lançamento de diagnóstico (retoque) e sua entrada na agenda.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Servico


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
            s.add(Animal(numero="401", sit_rep="Ins.", ativo=True))
            s.add(Servico(numero_matriz="401", data_servico=date(2026, 6, 1), ult_ocorrencia=1))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestRegistrarDiagnostico:
    def test_marca_retoque(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        assert r.status_code == 200
        assert r.json()["retoque"] is True
        assert r.json()["diagnostico"] == "POSITIVO"

    def test_reconfirmada_desliga_retoque(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-20", "resultado": "reconfirmada",
        })
        assert r.json()["retoque"] is False
        assert r.json()["diagnostico"] == "POSITIVO"

    def test_matriz_sem_servico_da_404(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "999", "data_diagnostico": "2026-07-01", "resultado": "negativo",
        })
        assert r.status_code == 404

    def test_resultado_invalido_da_400(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "outra_coisa",
        })
        assert r.status_code == 400

    def test_indefinido_e_distinto_de_negativo(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "indefinido",
        })
        assert r.status_code == 200
        assert r.json()["diagnostico"] == "INDEFINIDO"
        assert r.json()["retoque"] is False

    def test_metodo_cio_de_repasse_persistido(self, client):
        r = client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "negativo",
            "metodo": "Cio de repasse",
        })
        assert r.status_code == 200
        assert r.json()["metodo_diagnostico"] == "Cio de repasse"
        assert r.json()["diagnostico"] == "NEGATIVO"


class TestRetoqueNaAgenda:
    def test_entra_na_agenda_no_dia_do_proximo_servico(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "retoque",
        })
        r = client.get("/agenda/", params={"data": "2026-07-01"})
        eventos = r.json()["eventos"]
        retoques = [e for e in eventos if e["numero_animal"] == "401" and "Retoque" in e["descricao"]]
        assert len(retoques) == 1
        # data_diagnostico (01/07) + dias_reinseminacao_referencia (22, media de 18-25) = 23/07
        assert retoques[0]["data"] == "2026-07-23"

    def test_sem_retoque_nao_aparece(self, client):
        client.post("/reproducao/diagnostico", json={
            "numero_matriz": "401", "data_diagnostico": "2026-07-01", "resultado": "reconfirmada",
        })
        r = client.get("/agenda/", params={"data": "2026-07-01"})
        eventos = r.json()["eventos"]
        assert not any("Retoque" in e["descricao"] for e in eventos)
