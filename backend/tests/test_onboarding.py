"""
Onboarding (checklist de primeiro acesso) — ver
fazenda/api/routers/onboarding.py e fazenda/models/onboarding.py.
"""
from __future__ import annotations

import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Usuario


class _FakeUser:
    id = 7
    papel = "operador"
    ativo = True
    username = "peao.teste"
    permissoes = "financeiro"


class _FakeOutroUser:
    id = 8
    papel = "operador"
    ativo = True
    username = "outro.teste"
    permissoes = "financeiro"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Usuario(id=7, username=_FakeUser.username, senha_hash="x", papel="operador", ativo=True, permissoes="financeiro"))
        s.add(Usuario(id=8, username=_FakeOutroUser.username, senha_hash="x", papel="operador", ativo=True, permissoes="financeiro"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


class TestOnboarding:
    def test_estado_inicial_nenhum_passo_concluido(self, client):
        r = client.get("/onboarding")
        assert r.status_code == 200
        body = r.json()
        assert len(body["passos"]) == 4
        assert all(not p["concluido"] for p in body["passos"])
        assert body["dispensado"] is False
        assert body["tudo_concluido"] is False

    def test_concluir_passo(self, client):
        r = client.post("/onboarding/passos/primeiro_lote/concluir")
        assert r.status_code == 200
        body = r.json()
        passo = next(p for p in body["passos"] if p["chave"] == "primeiro_lote")
        assert passo["concluido"] is True
        outros = [p for p in body["passos"] if p["chave"] != "primeiro_lote"]
        assert all(not p["concluido"] for p in outros)

    def test_concluir_passo_invalido_400(self, client):
        r = client.post("/onboarding/passos/chutando/concluir")
        assert r.status_code == 400

    def test_concluir_todos_os_passos_marca_tudo_concluido(self, client):
        for chave in ["primeiro_lote", "primeiro_lancamento", "conferir_agenda", "instalar_app"]:
            client.post(f"/onboarding/passos/{chave}/concluir")
        r = client.get("/onboarding")
        assert r.json()["tudo_concluido"] is True

    def test_concluir_o_mesmo_passo_duas_vezes_e_idempotente(self, client):
        client.post("/onboarding/passos/primeiro_lote/concluir")
        r = client.post("/onboarding/passos/primeiro_lote/concluir")
        body = r.json()
        assert sum(1 for p in body["passos"] if p["concluido"]) == 1

    def test_dispensar(self, client):
        r = client.post("/onboarding/dispensar")
        assert r.status_code == 200
        assert r.json()["dispensado"] is True
        assert client.get("/onboarding").json()["dispensado"] is True

    def test_isolado_por_usuario(self, client):
        client.post("/onboarding/passos/primeiro_lote/concluir")
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _FakeOutroUser()
        r = client.get("/onboarding")
        assert all(not p["concluido"] for p in r.json()["passos"])
