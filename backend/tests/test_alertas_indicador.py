"""
Alertas de indicador por limite — ver
fazenda/api/routers/alertas_indicador.py e fazenda/models/alerta_indicador.py.
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
    # get_fazenda_atual_id NÃO é sobrescrito de propósito: sem header de
    # autorização no TestClient, resolve para None, e exigir_contrato_ativo()
    # (dependência do router /notificacoes/) faz no-op quando fazenda_id é
    # None — mesmo padrão de tests/test_notificacoes.py.

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


class TestCatalogo:
    def test_catalogo_tem_indicadores(self, client):
        r = client.get("/alertas-indicador/catalogo")
        assert r.status_code == 200
        chaves = {c["chave"] for c in r.json()}
        assert "vacas_lactacao" in chaves
        assert "taxa_prenhez_pct" in chaves


class TestCrudAlertas:
    def test_criar_e_listar(self, client):
        r = client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": "<", "valor_limite": 5})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["indicador_chave"] == "vacas_lactacao"
        assert body["valor_atual"] == 0
        # banco vazio: 0 vacas em lactação < 5 -> disparado
        assert body["disparado"] is True

        r_lista = client.get("/alertas-indicador")
        assert r_lista.status_code == 200
        assert len(r_lista.json()) == 1

    def test_indicador_invalido_400(self, client):
        r = client.post("/alertas-indicador", json={"indicador_chave": "chutando", "operador": "<", "valor_limite": 5})
        assert r.status_code == 400

    def test_operador_invalido_400(self, client):
        r = client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": "==", "valor_limite": 5})
        assert r.status_code == 400

    def test_editar(self, client):
        criado = client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": "<", "valor_limite": 5}).json()
        r = client.put(f"/alertas-indicador/{criado['id']}", json={"valor_limite": 100, "ativo": False})
        assert r.status_code == 200
        assert r.json()["valor_limite"] == 100
        assert r.json()["ativo"] is False

    def test_editar_de_outro_usuario_404(self, client):
        criado = client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": "<", "valor_limite": 5}).json()
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _FakeOutroUser()
        r = client.put(f"/alertas-indicador/{criado['id']}", json={"valor_limite": 1})
        assert r.status_code == 404

    def test_excluir(self, client):
        criado = client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": "<", "valor_limite": 5}).json()
        r = client.delete(f"/alertas-indicador/{criado['id']}")
        assert r.status_code == 200
        assert client.get("/alertas-indicador").json() == []

    def test_condicao_nao_atendida_disparado_false(self, client):
        r = client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": ">", "valor_limite": 5})
        assert r.json()["disparado"] is False


class TestNotificacoes:
    def test_alerta_disparado_aparece_no_sino(self, client):
        client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": "<", "valor_limite": 5})
        r = client.get("/notificacoes/")
        assert r.status_code == 200
        itens = [i for i in r.json()["itens"] if i["tipo"] == "alerta_indicador"]
        assert len(itens) == 1
        assert "Vacas em lactação" in itens[0]["descricao"]

    def test_alerta_nao_disparado_nao_aparece(self, client):
        client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": ">", "valor_limite": 5})
        r = client.get("/notificacoes/")
        itens = [i for i in r.json()["itens"] if i["tipo"] == "alerta_indicador"]
        assert itens == []

    def test_alerta_inativo_nao_aparece(self, client):
        criado = client.post("/alertas-indicador", json={"indicador_chave": "vacas_lactacao", "operador": "<", "valor_limite": 5}).json()
        client.put(f"/alertas-indicador/{criado['id']}", json={"ativo": False})
        r = client.get("/notificacoes/")
        itens = [i for i in r.json()["itens"] if i["tipo"] == "alerta_indicador"]
        assert itens == []
