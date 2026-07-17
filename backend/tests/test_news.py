"""
Agregador de notícias "News" (botão no topo do site) — cadastro de fontes
(só admin) + leitura filtrada por palavra-chave, últimos 3 dias por padrão,
com "ver_tudo" para o histórico completo. Uma fonte com erro de busca nunca
derruba as outras. Nunca faz chamada de rede de verdade nestes testes — o
fetch (`buscar_noticias_fonte`) é substituído por um dublê.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import FonteNews, NoticiaNews


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "admin_teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


@pytest.fixture
def client_operador():
    """Usuário sem papel admin — só pra confirmar que o cadastro de fontes bloqueia."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeOperador:
        id = 2
        papel = "operador"
        ativo = True
        username = "operador_teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeOperador()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestCadastroFontesAdmin:
    def test_admin_cria_lista_edita_exclui(self, client):
        c, _ = client
        r = c.post("/news/fontes", json={"nome": "Site Teste", "url": "https://exemplo.com/feed"})
        assert r.status_code == 200, r.text
        fid = r.json()["id"]

        r = c.get("/news/fontes")
        assert r.status_code == 200
        assert any(f["nome"] == "Site Teste" for f in r.json())

        r = c.put(f"/news/fontes/{fid}", json={"nome": "Site Teste 2", "url": "https://exemplo.com/feed2", "ativo": False})
        assert r.status_code == 200
        assert r.json()["nome"] == "Site Teste 2"
        assert r.json()["ativo"] is False

        r = c.delete(f"/news/fontes/{fid}")
        assert r.status_code == 200
        assert r.json()["excluido"] is True

    def test_nome_duplicado_da_erro(self, client):
        c, _ = client
        c.post("/news/fontes", json={"nome": "Duplicado", "url": "https://a.com"})
        r = c.post("/news/fontes", json={"nome": "Duplicado", "url": "https://b.com"})
        assert r.status_code == 409

    def test_operador_nao_pode_gerenciar_fontes(self, client_operador):
        c, _ = client_operador
        r = c.post("/news/fontes", json={"nome": "X", "url": "https://x.com"})
        assert r.status_code == 403
        r = c.get("/news/fontes")
        assert r.status_code == 403


class TestListagemNoticias:
    def test_busca_filtra_por_palavra_chave_e_grava(self, client, monkeypatch):
        c, engine = client
        with Session(engine) as s:
            s.add(FonteNews(nome="Fonte A", url="https://fontea.com/feed"))
            s.commit()

        def fake_buscar(url):
            return [
                {"manchete": "Preço do leite sobe", "resumo": "Pecuária leiteira em alta", "link": "https://fontea.com/1", "data": datetime.utcnow()},
                {"manchete": "Notícia de soja", "resumo": "Nada a ver", "link": "https://fontea.com/2", "data": datetime.utcnow()},
            ]

        monkeypatch.setattr("fazenda.api.routers.news.buscar_noticias_fonte", fake_buscar)

        r = c.get("/news/")
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["janela_dias"] == 3
        assert len(dados["fontes"]) == 1
        fonte = dados["fontes"][0]
        assert fonte["fonte"]["erro"] is None
        assert len(fonte["noticias"]) == 1
        assert fonte["noticias"][0]["manchete"] == "Preço do leite sobe"

        with Session(engine) as s:
            todas = s.exec(select(NoticiaNews)).all()
            assert len(todas) == 1  # a de soja nunca foi gravada (filtrada antes de salvar)

    def test_fonte_com_erro_nao_derruba_as_outras(self, client, monkeypatch):
        c, engine = client
        with Session(engine) as s:
            s.add(FonteNews(nome="Fonte Com Erro", url="https://quebrada.com"))
            s.add(FonteNews(nome="Fonte OK", url="https://ok.com/feed"))
            s.commit()

        def fake_buscar(url):
            if "quebrada" in url:
                raise RuntimeError("Não foi possível localizar um feed RSS/Atom válido neste site")
            return [{"manchete": "Ordenha robotizada cresce no Brasil", "resumo": "Free stall e compost barn", "link": "https://ok.com/1", "data": datetime.utcnow()}]

        monkeypatch.setattr("fazenda.api.routers.news.buscar_noticias_fonte", fake_buscar)

        r = c.get("/news/")
        assert r.status_code == 200, r.text
        por_nome = {f["fonte"]["nome"]: f for f in r.json()["fontes"]}
        assert por_nome["Fonte Com Erro"]["fonte"]["erro"]
        assert por_nome["Fonte Com Erro"]["noticias"] == []
        assert por_nome["Fonte OK"]["fonte"]["erro"] is None
        assert len(por_nome["Fonte OK"]["noticias"]) == 1

        with Session(engine) as s:
            fonte_erro = s.exec(select(FonteNews).where(FonteNews.nome == "Fonte Com Erro")).first()
            assert fonte_erro.ultimo_erro

    def test_nao_rebusca_a_mesma_fonte_dentro_de_1_hora(self, client, monkeypatch):
        c, engine = client
        with Session(engine) as s:
            s.add(FonteNews(nome="Fonte B", url="https://fonteb.com/feed"))
            s.commit()

        chamadas = {"n": 0}

        def fake_buscar(url):
            chamadas["n"] += 1
            return [{"manchete": "Preço do leite estável", "resumo": "leite", "link": "https://fonteb.com/1", "data": datetime.utcnow()}]

        monkeypatch.setattr("fazenda.api.routers.news.buscar_noticias_fonte", fake_buscar)

        c.get("/news/")
        c.get("/news/")
        c.get("/news/")
        assert chamadas["n"] == 1

    def test_ver_tudo_mostra_noticias_com_mais_de_3_dias(self, client, monkeypatch):
        c, engine = client
        with Session(engine) as s:
            fonte = FonteNews(nome="Fonte C", url="https://fontec.com/feed")
            s.add(fonte)
            s.commit()
            s.refresh(fonte)
            s.add(NoticiaNews(
                fonte_id=fonte.id, manchete="Matéria antiga sobre leite", resumo="leite",
                link="https://fontec.com/antiga", data_publicacao=datetime.utcnow() - timedelta(days=10),
                capturado_em=datetime.utcnow() - timedelta(days=10),
            ))
            s.commit()

        monkeypatch.setattr("fazenda.api.routers.news.buscar_noticias_fonte", lambda url: [])

        r = c.get("/news/")
        assert r.status_code == 200
        assert r.json()["fontes"][0]["noticias"] == []

        r = c.get("/news/", params={"ver_tudo": True})
        assert r.status_code == 200
        noticias = r.json()["fontes"][0]["noticias"]
        assert len(noticias) == 1
        assert noticias[0]["manchete"] == "Matéria antiga sobre leite"

    def test_fonte_inativa_nao_aparece(self, client, monkeypatch):
        c, engine = client
        with Session(engine) as s:
            s.add(FonteNews(nome="Fonte Inativa", url="https://inativa.com", ativo=False))
            s.commit()
        monkeypatch.setattr("fazenda.api.routers.news.buscar_noticias_fonte", lambda url: [])
        r = c.get("/news/")
        assert r.status_code == 200
        assert r.json()["fontes"] == []
