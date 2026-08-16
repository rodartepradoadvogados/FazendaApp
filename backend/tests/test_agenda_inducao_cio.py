"""
Alerta "Observar cio" na Agenda — dispara na janela de 2 a 5 dias após uma
aplicação de indução de cio (PGF2α/Cloprostenol), e pára assim que o cio já
foi aproveitado (serviço mais recente do animal em data >= aplicação). Ver
AgendaEngine bloco "3b" e reproducao.py::ATIVIDADE_INDUCAO_CIO.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import Sanidade, Servico


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    yield main.app, engine
    main.app.dependency_overrides.clear()


def _client(app):
    return TestClient(app)


def _inducao(engine, numero="101", data_aplicacao=date(2026, 8, 10), produto="Cloprostenol"):
    with Session(engine) as s:
        s.add(Sanidade(numero_matriz=numero, data_aplicacao=data_aplicacao, produto=produto, atividade="Indução de cio"))
        s.commit()


def test_alerta_dentro_da_janela_de_2_a_5_dias(setup):
    app, engine = setup
    _inducao(engine, data_aplicacao=date(2026, 8, 10))
    c = _client(app)
    # 3 dias depois (dentro de 2-5) — deve alertar.
    r = c.get("/agenda/?data=2026-08-13&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"] if e["numero_animal"] == "101"]
    assert any("Observar cio" in d for d in descricoes)


def test_sem_alerta_no_dia_seguinte_a_aplicacao(setup):
    """1 dia depois — ainda fora da janela de 2 a 5 dias."""
    app, engine = setup
    _inducao(engine, data_aplicacao=date(2026, 8, 10))
    c = _client(app)
    r = c.get("/agenda/?data=2026-08-11&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"] if e["numero_animal"] == "101"]
    assert not any("Observar cio" in d for d in descricoes)


def test_sem_alerta_depois_de_6_dias(setup):
    app, engine = setup
    _inducao(engine, data_aplicacao=date(2026, 8, 10))
    c = _client(app)
    r = c.get("/agenda/?data=2026-08-17&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"] if e["numero_animal"] == "101"]
    assert not any("Observar cio" in d for d in descricoes)


def test_para_de_alertar_quando_cio_ja_foi_aproveitado(setup):
    """Serviço (IA) lançado depois da aplicação — o cio já foi aproveitado,
    não faz mais sentido continuar pedindo pra observar."""
    app, engine = setup
    _inducao(engine, data_aplicacao=date(2026, 8, 10))
    with Session(engine) as s:
        s.add(Servico(numero_matriz="101", data_servico=date(2026, 8, 12), ult_ocorrencia=1, tipo_servico="IA"))
        s.commit()
    c = _client(app)
    r = c.get("/agenda/?data=2026-08-13&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"] if e["numero_animal"] == "101"]
    assert not any("Observar cio" in d for d in descricoes)
