"""
Testes da sugestão de movimentação de lote aparecendo na Agenda, incluindo o
parâmetro de agendamento (dia fixo da semana × na própria data do parâmetro)
e o fluxo de cancelar (dispensar) a sugestão.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Lote, PesagemCorporal


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


def _preparar_sugestao(engine):
    with Session(engine) as s:
        s.add(Lote(codigo="02", nome="Aptas", peso_min=300))
        s.add(Animal(numero="900", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Recém-chegadas", ativo=True))
        s.commit()
        s.add(PesagemCorporal(numero_matriz="900", data_pesagem=date.today(), peso_kg=350))
        s.commit()


class TestParametroAgendamento:
    def test_default_e_na_data_parametro(self, client):
        c, engine = client
        r = c.get("/movimentacoes/parametro-agendamento")
        assert r.status_code == 200
        assert r.json()["modo"] == "na_data_parametro"

    def test_salvar_e_ler_dia_fixo_semana(self, client):
        c, engine = client
        r = c.put("/movimentacoes/parametro-agendamento", json={"modo": "dia_fixo_semana", "dia_semana": 4})
        assert r.status_code == 200
        assert r.json()["modo"] == "dia_fixo_semana"
        assert r.json()["dia_semana"] == 4
        r2 = c.get("/movimentacoes/parametro-agendamento")
        assert r2.json()["dia_semana"] == 4

    def test_modo_invalido_rejeitado(self, client):
        c, engine = client
        r = c.put("/movimentacoes/parametro-agendamento", json={"modo": "invalido", "dia_semana": 0})
        assert r.status_code == 400

    def test_dia_semana_invalido_rejeitado(self, client):
        c, engine = client
        r = c.put("/movimentacoes/parametro-agendamento", json={"modo": "dia_fixo_semana", "dia_semana": 9})
        assert r.status_code == 400


class TestSugestaoNaAgenda:
    def test_modo_na_data_parametro_aparece_todo_dia(self, client):
        c, engine = client
        _preparar_sugestao(engine)
        r = c.get("/agenda/", params={"data": date.today().isoformat()})
        assert r.status_code == 200
        eventos = r.json()["eventos"]
        alvo = next((e for e in eventos if e.get("tipo") == "sugestao_movimentacao" and e["numero_animal"] == "900"), None)
        assert alvo is not None
        # descrição mostra lote atual E lote de destino sugerido
        assert "01 - Recém-chegadas" in alvo["descricao"]
        assert "02" in alvo["descricao"]
        assert alvo["motivo"]

    def test_modo_dia_fixo_semana_so_aparece_no_dia_configurado(self, client):
        c, engine = client
        _preparar_sugestao(engine)
        hoje = date.today()
        dia_diferente = (hoje.weekday() + 1) % 7

        c.put("/movimentacoes/parametro-agendamento", json={"modo": "dia_fixo_semana", "dia_semana": dia_diferente})
        r = c.get("/agenda/", params={"data": hoje.isoformat()})
        eventos = r.json()["eventos"]
        assert not any(e.get("tipo") == "sugestao_movimentacao" for e in eventos)

        c.put("/movimentacoes/parametro-agendamento", json={"modo": "dia_fixo_semana", "dia_semana": hoje.weekday()})
        r2 = c.get("/agenda/", params={"data": hoje.isoformat()})
        eventos2 = r2.json()["eventos"]
        assert any(e.get("tipo") == "sugestao_movimentacao" and e["numero_animal"] == "900" for e in eventos2)

    def test_cancelar_sugestao_faz_ela_sumir(self, client):
        c, engine = client
        _preparar_sugestao(engine)
        r = c.get("/agenda/", params={"data": date.today().isoformat()})
        alvo = next(e for e in r.json()["eventos"] if e.get("tipo") == "sugestao_movimentacao" and e["numero_animal"] == "900")

        r2 = c.post("/agenda/realizados", json={"evento_id": alvo["id"]})
        assert r2.status_code == 200

        r3 = c.get("/agenda/", params={"data": date.today().isoformat()})
        assert not any(e.get("tipo") == "sugestao_movimentacao" and e["numero_animal"] == "900" for e in r3.json()["eventos"])

    def test_aceitar_sugestao_move_animal_e_some_da_agenda(self, client):
        c, engine = client
        _preparar_sugestao(engine)
        r = c.post("/movimentacoes/mover", json={
            "data_movimento": date.today().isoformat(), "motivo": "Aptidão",
            "lote_destino_codigo": "02", "animais": ["900"],
        })
        assert r.status_code == 200
        assert r.json()["movidos"] == 1

        r2 = c.get("/agenda/", params={"data": date.today().isoformat()})
        assert not any(e.get("tipo") == "sugestao_movimentacao" and e["numero_animal"] == "900" for e in r2.json()["eventos"])
