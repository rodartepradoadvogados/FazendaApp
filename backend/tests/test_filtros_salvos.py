"""
Filtros salvos — ver fazenda/api/routers/filtros_salvos.py e
fazenda/models/filtro_salvo.py.
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
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


class TestFiltrosSalvos:
    def test_criar_e_listar(self, client):
        r = client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "Este mês", "filtros": {"centro": "Leite", "inicio": "2026-07-01"}})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["nome"] == "Este mês"
        assert body["filtros"] == {"centro": "Leite", "inicio": "2026-07-01"}

        r_lista = client.get("/filtros-salvos", params={"tela": "financeiro_extrato"})
        assert r_lista.status_code == 200
        assert len(r_lista.json()) == 1
        assert r_lista.json()[0]["nome"] == "Este mês"

    def test_isolado_por_tela(self, client):
        client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "A", "filtros": {}})
        client.post("/filtros-salvos", json={"tela": "financeiro_fluxo", "nome": "B", "filtros": {}})
        r = client.get("/filtros-salvos", params={"tela": "financeiro_extrato"})
        assert [f["nome"] for f in r.json()] == ["A"]

    def test_nome_duplicado_na_mesma_tela_400(self, client):
        client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "A", "filtros": {}})
        r = client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "A", "filtros": {"x": 1}})
        assert r.status_code == 400

    def test_mesmo_nome_em_telas_diferentes_ok(self, client):
        r1 = client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "A", "filtros": {}})
        r2 = client.post("/filtros-salvos", json={"tela": "financeiro_fluxo", "nome": "A", "filtros": {}})
        assert r1.status_code == 201
        assert r2.status_code == 201

    def test_isolado_por_usuario(self, client):
        client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "Só meu", "filtros": {}})
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _FakeOutroUser()
        r = client.get("/filtros-salvos", params={"tela": "financeiro_extrato"})
        assert r.json() == []

    def test_excluir(self, client):
        criado = client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "Temp", "filtros": {}}).json()
        r = client.delete(f"/filtros-salvos/{criado['id']}")
        assert r.status_code == 200
        assert client.get("/filtros-salvos", params={"tela": "financeiro_extrato"}).json() == []

    def test_excluir_de_outro_usuario_404(self, client):
        criado = client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "Alheio", "filtros": {}}).json()
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _FakeOutroUser()
        r = client.delete(f"/filtros-salvos/{criado['id']}")
        assert r.status_code == 404

    def test_excluir_inexistente_404(self, client):
        r = client.delete("/filtros-salvos/99999")
        assert r.status_code == 404

    def test_tela_vazia_400(self, client):
        r = client.post("/filtros-salvos", json={"tela": "", "nome": "A", "filtros": {}})
        assert r.status_code == 400

    def test_nome_vazio_400(self, client):
        r = client.post("/filtros-salvos", json={"tela": "financeiro_extrato", "nome": "  ", "filtros": {}})
        assert r.status_code == 400
