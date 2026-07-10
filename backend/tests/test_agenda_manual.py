"""
Testes do evento manual de Agenda: vínculo a animal(is)/lote(s), tipo de
evento e recorrência (a cada N dias/meses).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers.agenda import _proxima_ocorrencia
from fazenda.models import AgendaManual


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


class TestCriarEventoManual:
    def test_cria_evento_com_varios_animais_e_tipo(self, client):
        c, engine = client
        r = c.post("/agenda/manual", json={
            "data_evento": "2026-08-01", "descricao": "Comprar vacina",
            "categoria": "Atividades", "numero_animal": "801,802,803", "tipo_evento": "Compra",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["numero_animal"] == "801,802,803"
        assert d["tipo_evento"] == "Compra"

    def test_cria_evento_vinculado_a_lotes(self, client):
        c, engine = client
        r = c.post("/agenda/manual", json={
            "data_evento": "2026-08-01", "descricao": "Trocar dieta", "lotes": "01,02",
        })
        assert r.status_code == 200
        assert r.json()["lotes"] == "01,02"

    def test_tipo_evento_invalido_e_rejeitado(self, client):
        c, engine = client
        r = c.post("/agenda/manual", json={
            "data_evento": "2026-08-01", "descricao": "x", "tipo_evento": "Aluguel",
        })
        assert r.status_code == 400

    def test_recorrente_sem_intervalo_e_rejeitado(self, client):
        c, engine = client
        r = c.post("/agenda/manual", json={
            "data_evento": "2026-08-01", "descricao": "x", "recorrente": True,
        })
        assert r.status_code == 400

    def test_recorrente_com_dias_e_meses_e_rejeitado(self, client):
        c, engine = client
        r = c.post("/agenda/manual", json={
            "data_evento": "2026-08-01", "descricao": "x", "recorrente": True,
            "intervalo_dias": 15, "intervalo_meses": 1,
        })
        assert r.status_code == 400


class TestRecorrencia:
    def test_gera_ocorrencias_ate_hoje(self, client):
        c, engine = client
        base = date.today() - timedelta(days=40)
        with Session(engine) as s:
            s.add(AgendaManual(
                data_evento=base, descricao="Vermifugar", categoria="Atividades",
                recorrente=True, intervalo_dias=15,
            ))
            s.commit()

        # A rota GET /agenda/ dispara a geração "lazy pull" das próximas ocorrências.
        r = c.get("/agenda/?dias=0")
        assert r.status_code == 200

        esperadas = []
        proxima = _proxima_ocorrencia(base, 15, None)
        while proxima <= date.today():
            esperadas.append(proxima)
            proxima = _proxima_ocorrencia(proxima, 15, None)

        with Session(engine) as s:
            gerados = s.exec(
                select(AgendaManual).where(AgendaManual.origem_recorrencia_id != None)  # noqa: E711
            ).all()
            assert {g.data_evento for g in gerados} == set(esperadas)

    def test_nao_duplica_ocorrencias_ja_geradas(self, client):
        c, engine = client
        base = date.today() - timedelta(days=100)
        with Session(engine) as s:
            s.add(AgendaManual(
                data_evento=base, descricao="Vermifugar", categoria="Atividades",
                recorrente=True, intervalo_meses=1,
            ))
            s.commit()

        c.get("/agenda/?dias=0")
        r1 = c.get("/agenda/?dias=0")
        assert r1.status_code == 200

        with Session(engine) as s:
            total_primeira = len(s.exec(
                select(AgendaManual).where(AgendaManual.origem_recorrencia_id != None)  # noqa: E711
            ).all())

        c.get("/agenda/?dias=0")

        with Session(engine) as s:
            total_segunda = len(s.exec(
                select(AgendaManual).where(AgendaManual.origem_recorrencia_id != None)  # noqa: E711
            ).all())

        assert total_primeira == total_segunda
        assert total_primeira > 0
