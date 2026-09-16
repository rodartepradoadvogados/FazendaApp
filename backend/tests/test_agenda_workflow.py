"""
Testes do workflow da agenda: marcar evento como realizado (some da agenda)
e a chave estável usada para identificar cada evento.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import AgendaManual
from fazenda.rules.agenda_engine import AgendaItem


class TestChaveEvento:
    def test_chave_estavel_para_o_mesmo_evento(self):
        a = AgendaItem(data=date(2026, 3, 1), categoria="Reprodutivo", descricao="Scratch", numero_animal="123")
        b = AgendaItem(data=date(2026, 3, 1), categoria="Reprodutivo", descricao="Scratch", numero_animal="123")
        assert a.chave == b.chave

    def test_chave_muda_com_qualquer_campo(self):
        base = AgendaItem(data=date(2026, 3, 1), categoria="Reprodutivo", descricao="Scratch", numero_animal="123")
        outra_data = AgendaItem(data=date(2026, 3, 2), categoria="Reprodutivo", descricao="Scratch", numero_animal="123")
        outro_animal = AgendaItem(data=date(2026, 3, 1), categoria="Reprodutivo", descricao="Scratch", numero_animal="456")
        assert base.chave != outra_data.chave
        assert base.chave != outro_animal.chave

    def test_chave_muda_com_origem_id_diferente(self):
        """Bug relatado pelo usuário em 16/09/2026: dois eventos MANUAIS com a
        mesma data/categoria/descrição e sem animal vinculado geravam a MESMA
        chave (sem `origem_id`, o hash só olhava esses 4 campos) — marcar um
        como realizado marcava os dois juntos, silenciosamente. `origem_id`
        (o id real de AgendaManual) desambigua; eventos automáticos (sem
        origem_id, sempre None) continuam com o hash de antes."""
        um = AgendaItem(data=date(2026, 3, 1), categoria="Atividades", descricao="Evento manual", origem_id=1)
        outro = AgendaItem(data=date(2026, 3, 1), categoria="Atividades", descricao="Evento manual", origem_id=2)
        assert um.chave != outro.chave

    def test_chave_sem_origem_id_preserva_o_hash_de_sempre(self):
        """Eventos automáticos (nunca têm origem_id) não podem trocar de
        chave com esta correção — resetaria todo "realizado" já gravado.
        Confere contra o cálculo manual da fórmula de sempre (4 campos, sem
        nenhum sufixo novo)."""
        import hashlib
        auto = AgendaItem(data=date(2026, 3, 1), categoria="Reprodutivo", descricao="Scratch", numero_animal="123")
        esperado_de_sempre = hashlib.sha1(b"2026-03-01|Reprodutivo|Scratch|123").hexdigest()[:16]
        assert auto.chave == esperado_de_sempre


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestMarcarRealizado:
    def test_marcar_evento_manual_faz_ele_sumir_da_agenda(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(AgendaManual(data_evento=date(2026, 3, 1), descricao="Evento de teste", categoria="Atividades"))
            s.commit()

        r1 = c.get("/agenda/", params={"data": "2026-01-01"})
        assert r1.status_code == 200
        eventos = r1.json()["eventos"]
        alvo = next(e for e in eventos if e["descricao"] == "Evento de teste")
        assert alvo["fonte"] == "manual"

        r2 = c.post("/agenda/realizados", json={"evento_id": alvo["id"]})
        assert r2.status_code == 200

        r3 = c.get("/agenda/", params={"data": "2026-01-01"})
        eventos3 = r3.json()["eventos"]
        assert all(e["descricao"] != "Evento de teste" for e in eventos3)

    def test_desmarcar_traz_o_evento_de_volta(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(AgendaManual(data_evento=date(2026, 3, 1), descricao="Evento reversível", categoria="Atividades"))
            s.commit()

        eventos = c.get("/agenda/", params={"data": "2026-01-01"}).json()["eventos"]
        alvo = next(e for e in eventos if e["descricao"] == "Evento reversível")
        c.post("/agenda/realizados", json={"evento_id": alvo["id"]})

        r = c.delete(f"/agenda/realizados/{alvo['id']}")
        assert r.status_code == 200

        eventos2 = c.get("/agenda/", params={"data": "2026-01-01"}).json()["eventos"]
        assert any(e["descricao"] == "Evento reversível" for e in eventos2)

    def test_dois_eventos_manuais_identicos_tem_ids_distintos(self, client):
        """Bug relatado pelo usuário em 16/09/2026: dois eventos manuais com a
        mesma data/categoria/descrição e sem animal vinculado colidiam na
        mesma `chave` — marcar um como realizado marcava os dois juntos."""
        c, engine = client
        with Session(engine) as s:
            s.add(AgendaManual(data_evento=date(2026, 3, 1), descricao="Evento igual", categoria="Atividades"))
            s.add(AgendaManual(data_evento=date(2026, 3, 1), descricao="Evento igual", categoria="Atividades"))
            s.commit()

        eventos = c.get("/agenda/", params={"data": "2026-01-01"}).json()["eventos"]
        iguais = [e for e in eventos if e["descricao"] == "Evento igual"]
        assert len(iguais) == 2
        assert iguais[0]["id"] != iguais[1]["id"]

        c.post("/agenda/realizados", json={"evento_id": iguais[0]["id"]})

        eventos2 = c.get("/agenda/", params={"data": "2026-01-01"}).json()["eventos"]
        restantes = [e for e in eventos2 if e["descricao"] == "Evento igual"]
        assert len(restantes) == 1

    def test_marcar_duas_vezes_e_idempotente(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(AgendaManual(data_evento=date(2026, 3, 1), descricao="Evento duplicado", categoria="Atividades"))
            s.commit()

        eventos = c.get("/agenda/", params={"data": "2026-01-01"}).json()["eventos"]
        alvo = next(e for e in eventos if e["descricao"] == "Evento duplicado")
        assert c.post("/agenda/realizados", json={"evento_id": alvo["id"]}).status_code == 200
        assert c.post("/agenda/realizados", json={"evento_id": alvo["id"]}).status_code == 200
