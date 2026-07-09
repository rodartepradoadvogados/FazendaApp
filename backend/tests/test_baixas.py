"""Testes de baixa de animal (Rebanho > Baixar animal) — óbito/descarte."""
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

    from fazenda.api.routers.cadastro import seed_motivos_baixa

    with TestClient(main.app) as c:
        with Session(engine) as s:
            s.add(Animal(numero="900", grupo_primario="01 - Alta", ativo=True))
            s.add(Animal(numero="901", grupo_primario="01 - Alta", ativo=True))
            seed_motivos_baixa(s)
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestOpcoes:
    def test_lista_tipos_e_motivos(self, client):
        r = client.get("/baixas/motivos")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["tipos_baixa"] == ["morte", "descarte_voluntario", "descarte_involuntario"]
        assert "venda" in corpo["motivos"] and "doenca" in corpo["motivos"]
        assert "Mastite" in corpo["motivos_doenca"]


class TestRegistrarBaixa:
    def test_baixa_por_morte_doenca_marca_animal_inativo(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "morte", "motivo": "doenca",
            "motivo_doenca": "Mastite", "data_baixa": "2026-07-08", "observacao": "teste",
        })
        assert r.status_code == 200
        assert r.json()["baixados"] == 1
        animal = client.get("/animais/900").json()
        assert animal["ativo"] is False
        assert animal["data_baixa"] == "2026-07-08"
        assert animal["motivo_baixa"] == "Mastite"

    def test_baixa_por_venda_exige_valor_e_cliente(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "data_baixa": "2026-07-08",
        })
        assert r.status_code == 400

    def test_baixa_por_venda_com_valor_e_cliente(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "descarte_voluntario", "motivo": "venda",
            "valor": 3500.0, "cliente": "Frigorífico X", "data_baixa": "2026-07-08",
        })
        assert r.status_code == 200
        historico = client.get("/baixas/").json()
        assert historico[0]["valor"] == 3500.0
        assert historico[0]["cliente"] == "Frigorífico X"

    def test_baixa_doenca_sem_motivo_doenca_da_erro(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "morte", "motivo": "doenca",
            "data_baixa": "2026-07-08",
        })
        assert r.status_code == 400

    def test_baixa_em_lote_varios_animais(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900", "901"], "tipo_baixa": "morte", "motivo": "acidente",
            "data_baixa": "2026-07-08",
        })
        assert r.status_code == 200
        assert r.json()["baixados"] == 2
        assert client.get("/animais/900").json()["ativo"] is False
        assert client.get("/animais/901").json()["ativo"] is False

    def test_animal_inexistente_reportado_sem_quebrar_os_demais(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900", "999"], "tipo_baixa": "morte", "motivo": "abate",
            "data_baixa": "2026-07-08",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["baixados"] == 1
        assert corpo["nao_encontrados"] == ["999"]

    def test_tipo_baixa_invalido_rejeitado(self, client):
        r = client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "sumiu", "motivo": "abate", "data_baixa": "2026-07-08",
        })
        assert r.status_code == 400

    def test_lista_baixas_ordenada_por_data_desc(self, client):
        client.post("/baixas/", json={
            "animais": ["900"], "tipo_baixa": "morte", "motivo": "abate", "data_baixa": "2026-07-01",
        })
        client.post("/baixas/", json={
            "animais": ["901"], "tipo_baixa": "morte", "motivo": "acidente", "data_baixa": "2026-07-08",
        })
        historico = client.get("/baixas/").json()
        assert historico[0]["numero_animal"] == "901"
        assert historico[1]["numero_animal"] == "900"
