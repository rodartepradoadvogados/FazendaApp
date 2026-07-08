"""
Testes do fluxo de aprovação de exclusão: operador solicita, fica pendente,
admin aprova (executa a exclusão) ou rejeita.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal


class _FakeAdmin:
    id = 1
    papel = "admin"
    ativo = True
    username = "admin_teste"


class _FakeOperador:
    id = 2
    papel = "operador"
    ativo = True
    username = "operador_teste"


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    database.get_session

    main.app.dependency_overrides[database.get_session] = _get_session_override

    with Session(engine) as s:
        s.add(Animal(numero="501", ativo=True))
        s.commit()

    yield main.app, engine
    main.app.dependency_overrides.clear()


def _client_as(app, user):
    from fazenda.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestSolicitacaoOperador:
    def test_operador_nao_exclui_direto_fica_pendente(self, setup):
        app, engine = setup
        c = _client_as(app, _FakeOperador())
        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "501"})
        assert r.status_code == 200
        assert r.json()["status"] == "solicitado"

        with Session(engine) as s:
            from sqlmodel import select
            from fazenda.models import Animal as AnimalModel
            assert s.exec(select(AnimalModel).where(AnimalModel.numero == "501")).first() is not None

    def test_admin_ve_pendencia_do_operador(self, setup):
        app, engine = setup
        c_op = _client_as(app, _FakeOperador())
        c_op.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "501"})

        c_admin = _client_as(app, _FakeAdmin())
        r = c_admin.get("/exclusoes/pendentes")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["solicitado_por"] == "operador_teste"

    def test_operador_nao_acessa_pendentes(self, setup):
        app, engine = setup
        c_op = _client_as(app, _FakeOperador())
        r = c_op.get("/exclusoes/pendentes")
        assert r.status_code == 403

    def test_admin_aprova_e_executa_exclusao(self, setup):
        app, engine = setup
        c_op = _client_as(app, _FakeOperador())
        c_op.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "501"})

        c_admin = _client_as(app, _FakeAdmin())
        sol_id = c_admin.get("/exclusoes/pendentes").json()[0]["id"]
        r = c_admin.post(f"/exclusoes/pendentes/{sol_id}/aprovar")
        assert r.status_code == 200
        assert r.json()["aprovado"] is True

        from sqlmodel import select
        from fazenda.models import Animal as AnimalModel
        with Session(engine) as s:
            assert s.exec(select(AnimalModel).where(AnimalModel.numero == "501")).first() is None
        assert c_admin.get("/exclusoes/pendentes").json() == []

    def test_admin_rejeita_e_nao_exclui(self, setup):
        app, engine = setup
        c_op = _client_as(app, _FakeOperador())
        c_op.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "501"})

        c_admin = _client_as(app, _FakeAdmin())
        sol_id = c_admin.get("/exclusoes/pendentes").json()[0]["id"]
        r = c_admin.post(f"/exclusoes/pendentes/{sol_id}/rejeitar", json={"motivo": "não procede"})
        assert r.status_code == 200
        assert r.json()["rejeitado"] is True

        from sqlmodel import select
        from fazenda.models import Animal as AnimalModel
        with Session(engine) as s:
            assert s.exec(select(AnimalModel).where(AnimalModel.numero == "501")).first() is not None
        assert c_admin.get("/exclusoes/pendentes").json() == []

    def test_admin_ainda_exclui_direto(self, setup):
        app, engine = setup
        c_admin = _client_as(app, _FakeAdmin())
        r = c_admin.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "501"})
        assert r.json()["status"] == "excluido"

        from sqlmodel import select
        from fazenda.models import Animal as AnimalModel
        with Session(engine) as s:
            assert s.exec(select(AnimalModel).where(AnimalModel.numero == "501")).first() is None
