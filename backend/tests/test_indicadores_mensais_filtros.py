"""
Testes do filtro de período/dimensões em /reproducao/indicadores-mensais —
o gráfico interativo de Análise reprodutiva (cruzamento de métricas) deve
refletir o mesmo recorte escolhido nos filtros da tela, não o histórico
inteiro.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Servico


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


def _add_servico(engine, numero, data_servico, tipo_servico="Inseminação", diagnostico=None):
    with Session(engine) as s:
        s.add(Servico(numero_matriz=numero, data_servico=data_servico, tipo_servico=tipo_servico,
                       diagnostico=diagnostico))
        s.commit()


class TestFiltroPeriodo:
    def test_sem_filtro_traz_todos_os_meses(self, client):
        c, engine = client
        _add_servico(engine, "1", date(2026, 1, 10))
        _add_servico(engine, "2", date(2026, 3, 5))
        r = c.get("/reproducao/indicadores-mensais")
        assert r.status_code == 200
        assert r.json()["meses"] == ["2026-01", "2026-03"]

    def test_filtro_ini_fim_restringe_meses(self, client):
        c, engine = client
        _add_servico(engine, "1", date(2026, 1, 10))
        _add_servico(engine, "2", date(2026, 3, 5))
        r = c.get("/reproducao/indicadores-mensais", params={"ini": "2026-02-01", "fim": "2026-12-31"})
        assert r.json()["meses"] == ["2026-03"]
        assert r.json()["series"]["num_servicos"] == [1]


class TestFiltroDimensao:
    def test_filtro_tipo_servico_restringe_contagem(self, client):
        c, engine = client
        _add_servico(engine, "1", date(2026, 1, 10), tipo_servico="Inseminação")
        _add_servico(engine, "2", date(2026, 1, 12), tipo_servico="Cobertura")
        r_todos = c.get("/reproducao/indicadores-mensais")
        assert r_todos.json()["series"]["num_servicos"] == [2]

        r_filtrado = c.get("/reproducao/indicadores-mensais", params={"tipo_servico": "Inseminação"})
        assert r_filtrado.json()["series"]["num_servicos"] == [1]

    def test_filtro_dimensao_sem_correspondencia_zera_series(self, client):
        c, engine = client
        _add_servico(engine, "1", date(2026, 1, 10), tipo_servico="Inseminação")
        r = c.get("/reproducao/indicadores-mensais", params={"tipo_servico": "Cobertura"})
        assert r.json()["meses"] == []
