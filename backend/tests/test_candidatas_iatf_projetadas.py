"""Testes de GET /reproducao/protocolo-iatf/candidatas — candidatas à próxima
IATF com projeção de aptidão na data do próximo serviço (usado em
Histórico > Reprodução > Ciclos de IATF)."""
from __future__ import annotations

from datetime import date, timedelta

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
        yield c, engine

    main.app.dependency_overrides.clear()


def test_vazia_apta_continua_apta_projetada(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="1", sexo="F", ativo=True, sit_rep="Vaz. apt.", del_dias=60))
        # Ancora a próxima visita — último serviço do rebanho + intervalo padrão (21 dias).
        s.add(Servico(numero_matriz="1", data_servico=hoje - timedelta(days=10), ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    assert r.status_code == 200
    dados = r.json()
    cand = next(x for x in dados["candidatas"] if x["numero_matriz"] == "1")
    assert cand["motivo"] == "Vazia apta"
    assert cand["apta_na_proxima_visita"] is True
    assert cand["del_dias_projetado"] > cand["del_dias"]


def test_ainda_no_pev_na_data_da_visita_nao_e_apta_projetada(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        # DEL 10 hoje; próxima visita ~11 dias à frente (último serviço -10 + intervalo 21) —
        # DEL projetado ~21, ainda abaixo do PEV padrão (45) na maioria das fazendas.
        s.add(Animal(numero="2", sexo="F", ativo=True, sit_rep="Vaz. atr.", del_dias=10))
        s.add(Servico(numero_matriz="2", data_servico=hoje - timedelta(days=10), ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    dados = r.json()
    cand = next(x for x in dados["candidatas"] if x["numero_matriz"] == "2")
    assert cand["apta_na_proxima_visita"] is False


def test_diagnostico_negativo_sempre_apta(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="3", sexo="F", ativo=True, sit_rep=""))
        s.add(Servico(numero_matriz="3", data_servico=hoje - timedelta(days=5), ordem_tentativa=1,
                      diagnostico="NEGATIVO", ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    dados = r.json()
    cand = next(x for x in dados["candidatas"] if x["numero_matriz"] == "3")
    assert cand["motivo"] == "Diagnóstico negativo"
    assert cand["apta_na_proxima_visita"] is True
