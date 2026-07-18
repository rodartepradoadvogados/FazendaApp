"""
Agregador de notícias "News" (botão no topo do site) — cadastro de fontes
(só admin) + leitura filtrada por palavra-chave, últimos 3 dias por padrão,
com "ver_tudo" para o histórico completo. Uma fonte com erro de busca nunca
derruba as outras. Nunca faz chamada de rede de verdade nestes testes — o
fetch (`buscar_noticias_fonte`) é substituído por um dublê.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import FonteNews, LancamentoPendente, NoticiaNews


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
        pode_publicar_materias_blog = True

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


@pytest.fixture
def client_admin_sem_permissao_publicar():
    """Admin comum, mas SEM a permissão pode_publicar_materias_blog — confirma
    que essa permissão é independente de papel/admin (igual exigir_dono)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeAdminSemPermissao:
        id = 3
        papel = "admin"
        ativo = True
        username = "admin_sem_permissao"
        pode_publicar_materias_blog = False

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdminSemPermissao()

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
        pode_publicar_materias_blog = False

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


class TestLeituraPublicaSemLogin:
    """GET /news/ é aberto a qualquer visitante — a leitura do blog não exige
    login (só cadastro/publicação/edição continuam exigindo permissão)."""

    def test_lista_sem_qualquer_autenticacao(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        main.app.dependency_overrides[database.get_session] = _get_session_override
        # Nenhum override de get_current_user — simula visitante sem token algum.

        with TestClient(main.app) as c:
            with Session(engine) as s:
                s.add(FonteNews(nome="Fonte Pública", url="https://publica.com/feed"))
                s.commit()
            r = c.get("/news/")  # sem header Authorization

        main.app.dependency_overrides.clear()
        assert r.status_code == 200, r.text

    def test_fontes_admin_continuam_exigindo_login(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        main.app.dependency_overrides[database.get_session] = _get_session_override

        with TestClient(main.app) as c:
            r = c.post("/news/fontes", json={"nome": "X", "url": "https://x.com"})

        main.app.dependency_overrides.clear()
        assert r.status_code == 401


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


class TestTestarFonteAgora:
    """POST /news/fontes/{id}/testar — busca na hora, ignora o intervalo
    mínimo de 1h, para o admin conseguir testar uma correção sem esperar."""

    def test_testar_ignora_intervalo_minimo_e_retorna_sucesso(self, client, monkeypatch):
        c, engine = client
        with Session(engine) as s:
            fonte = FonteNews(nome="Fonte D", url="https://konted.com/feed", ultima_busca_em=datetime.utcnow())
            s.add(fonte)
            s.commit()
            s.refresh(fonte)
            fid = fonte.id

        monkeypatch.setattr(
            "fazenda.api.routers.news.buscar_noticias_fonte",
            lambda url: [{"manchete": "Preço do leite sobe", "resumo": "leite", "link": "https://konted.com/1", "data": datetime.utcnow()}],
        )

        r = c.post(f"/news/fontes/{fid}/testar")
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["ok"] is True
        assert dados["materias_novas"] == 1
        assert dados["erro"] is None

        with Session(engine) as s:
            fonte = s.get(FonteNews, fid)
            assert fonte.ultimo_erro is None
            assert fonte.ultima_busca_ok_em is not None

    def test_testar_retorna_erro_real_sem_derrubar_a_fonte(self, client, monkeypatch):
        c, engine = client
        with Session(engine) as s:
            s.add(FonteNews(nome="Fonte E", url="https://quebrada2.com"))
            s.commit()
        fid = c.get("/news/fontes").json()[0]["id"]

        def fake_buscar(url):
            raise RuntimeError("HTTP 403 ao acessar o site")

        monkeypatch.setattr("fazenda.api.routers.news.buscar_noticias_fonte", fake_buscar)

        r = c.post(f"/news/fontes/{fid}/testar")
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["ok"] is False
        assert "403" in dados["erro"]

        with Session(engine) as s:
            fonte = s.get(FonteNews, fid)
            assert fonte.ultimo_erro and "403" in fonte.ultimo_erro

    def test_operador_nao_pode_testar_fonte(self, client_operador):
        c, engine = client_operador
        with Session(engine) as s:
            s.add(FonteNews(nome="Fonte F", url="https://f.com"))
            s.commit()
            fid = s.exec(select(FonteNews)).first().id
        r = c.post(f"/news/fontes/{fid}/testar")
        assert r.status_code == 403

    def test_testar_fonte_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/news/fontes/999/testar")
        assert r.status_code == 404


class TestImportarNoticiasManual:
    """POST /news/manual — recebe matérias já apuradas por fora (ex.: robô
    agendado /milknews). Nunca publica direto: cada item vira um
    LancamentoPendente(tipo="noticia_manual") na mesma fila de aprovação do
    Telegram — só vira NoticiaNews de verdade quando o administrador aprova
    em /aprovacoes."""

    def test_cria_pendente_em_vez_de_publicar_direto(self, client):
        c, engine = client
        r = c.post("/news/manual", json={"itens": [
            {"fonte_nome": "MilkNews Diário", "manchete": "Preço do leite sobe", "resumo": "Pecuária leiteira em alta",
             "link": "https://milknews.example.com/1", "data_publicacao": "2026-07-15"},
        ]})
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["pendentes_criados"] == 1
        assert dados["duplicadas"] == 0
        assert dados["invalidas"] == 0

        with Session(engine) as s:
            # Nada publicado ainda — nem NoticiaNews, nem FonteNews criada.
            assert s.exec(select(NoticiaNews)).first() is None
            pend = s.exec(select(LancamentoPendente).where(LancamentoPendente.tipo == "noticia_manual")).first()
            assert pend is not None
            assert pend.status == "pendente"
            payload = json.loads(pend.payload)
            assert payload["manchete"] == "Preço do leite sobe"
            assert payload["link"] == "https://milknews.example.com/1"
            assert "Preço do leite sobe" in pend.resumo

    def test_ignora_item_invalido(self, client):
        c, _ = client
        r = c.post("/news/manual", json={"itens": [
            {"fonte_nome": "MilkNews Diário", "manchete": "", "link": "https://milknews.example.com/2"},
            {"fonte_nome": "MilkNews Diário", "manchete": "Nova matéria", "link": "https://milknews.example.com/3"},
        ]})
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["pendentes_criados"] == 1
        assert dados["invalidas"] == 1

    def test_ignora_link_ja_publicado(self, client):
        c, engine = client
        with Session(engine) as s:
            fonte = FonteNews(nome="MilkNews Diário", url="https://milknews.example.com/", manual=True)
            s.add(fonte)
            s.commit()
            s.refresh(fonte)
            s.add(NoticiaNews(fonte_id=fonte.id, manchete="Já existe", link="https://milknews.example.com/1"))
            s.commit()

        r = c.post("/news/manual", json={"itens": [
            {"fonte_nome": "MilkNews Diário", "manchete": "Já existe (de novo)", "link": "https://milknews.example.com/1"},
        ]})
        assert r.status_code == 200, r.text
        assert r.json()["duplicadas"] == 1

    def test_nao_duplica_pendente_entre_execucoes_do_robo(self, client):
        c, _ = client
        item = {"fonte_nome": "MilkNews Diário", "manchete": "Matéria repetida", "link": "https://milknews.example.com/x"}
        r1 = c.post("/news/manual", json={"itens": [item]})
        assert r1.json()["pendentes_criados"] == 1
        r2 = c.post("/news/manual", json={"itens": [item]})
        assert r2.json()["pendentes_criados"] == 0
        assert r2.json()["duplicadas"] == 1

    def test_operador_nao_pode_importar_manual(self, client_operador):
        c, _ = client_operador
        r = c.post("/news/manual", json={"itens": []})
        assert r.status_code == 403


class TestAprovarNoticiaManual:
    """Aprovar um LancamentoPendente(tipo="noticia_manual") em /aprovacoes
    materializa a NoticiaNews de verdade; rejeitar não cria nada."""

    def test_aprovar_publica_a_noticia(self, client):
        c, engine = client
        c.post("/news/manual", json={"itens": [
            {"fonte_nome": "MilkNews Diário", "manchete": "Preço do leite sobe", "resumo": "leite em alta",
             "link": "https://milknews.example.com/1", "data_publicacao": "2026-07-15"},
        ]})
        pend_id = c.get("/aprovacoes").json()[0]["id"]

        r = c.post(f"/aprovacoes/{pend_id}/aprovar")
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            fonte = s.exec(select(FonteNews).where(FonteNews.nome == "MilkNews Diário")).first()
            assert fonte is not None and fonte.manual is True
            noticia = s.exec(select(NoticiaNews).where(NoticiaNews.link == "https://milknews.example.com/1")).first()
            assert noticia is not None
            assert noticia.manchete == "Preço do leite sobe"
            assert noticia.data_publicacao == datetime(2026, 7, 15)
            pend = s.get(LancamentoPendente, pend_id)
            assert pend.status == "aprovado"

    def test_rejeitar_nao_publica_nada(self, client):
        c, engine = client
        c.post("/news/manual", json={"itens": [
            {"fonte_nome": "MilkNews Diário", "manchete": "Matéria descartada", "link": "https://milknews.example.com/2"},
        ]})
        pend_id = c.get("/aprovacoes").json()[0]["id"]

        r = c.post(f"/aprovacoes/{pend_id}/rejeitar")
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            assert s.exec(select(NoticiaNews).where(NoticiaNews.link == "https://milknews.example.com/2")).first() is None
            assert s.get(LancamentoPendente, pend_id).status == "rejeitado"

    def test_fonte_manual_nunca_tenta_rss(self, client, monkeypatch):
        c, engine = client
        c.post("/news/manual", json={"itens": [
            {"fonte_nome": "MilkNews Diário", "manchete": "Matéria única", "link": "https://milknews.example.com/1"},
        ]})
        pend_id = c.get("/aprovacoes").json()[0]["id"]
        c.post(f"/aprovacoes/{pend_id}/aprovar")

        chamado = {"n": False}

        def fake_buscar(url):
            chamado["n"] = True
            raise RuntimeError("nunca deveria ser chamado para fonte manual")

        monkeypatch.setattr("fazenda.api.routers.news.buscar_noticias_fonte", fake_buscar)

        r = c.get("/news/")
        assert r.status_code == 200, r.text
        assert chamado["n"] is False
        fonte = r.json()["fontes"][0]
        assert fonte["fonte"]["erro"] is None
        assert len(fonte["noticias"]) == 1


class TestMateriaBlog:
    """POST /news/materias — "Adicionar matéria ao blog" (Configurações >
    News), exige a permissão pode_publicar_materias_blog, publica direto (sem
    fila de aprovação) sob a fonte fixa "Blog CowData". DELETE
    /news/materias/{id} exclui. Toda matéria nasce com revisado_final=False."""

    def test_publica_com_tres_fontes(self, client):
        c, engine = client
        r = c.post("/news/materias", json={
            "manchete": "Compost Barn reduz mastite",
            "materia": "Texto completo da matéria sobre compost barn...",
            "fontes": ["https://a.com/1", "https://b.com/2", "https://c.com/3"],
        })
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["manchete"] == "Compost Barn reduz mastite"
        assert dados["materia"] == "Texto completo da matéria sobre compost barn..."
        assert dados["fontes"] == ["https://a.com/1", "https://b.com/2", "https://c.com/3"]
        assert dados["link"] == "https://a.com/1"
        assert dados["data_publicacao"] is not None

        with Session(engine) as s:
            fonte = s.exec(select(FonteNews).where(FonteNews.nome == "Blog CowData")).first()
            assert fonte is not None
            assert fonte.manual is True
            noticia = s.get(NoticiaNews, dados["id"])
            assert noticia.fonte_id == fonte.id
            assert json.loads(noticia.fontes) == ["https://a.com/1", "https://b.com/2", "https://c.com/3"]
            assert noticia.revisado_final is False

    def test_publica_sem_fontes_gera_link_placeholder_unico(self, client):
        c, engine = client
        r1 = c.post("/news/materias", json={"manchete": "Matéria 1", "materia": "Corpo 1", "fontes": []})
        r2 = c.post("/news/materias", json={"manchete": "Matéria 2", "materia": "Corpo 2", "fontes": []})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["fontes"] == []
        assert r1.json()["link"].startswith("blog://")
        assert r1.json()["link"] != r2.json()["link"]

    def test_publica_com_uma_fonte(self, client):
        c, _ = client
        r = c.post("/news/materias", json={"manchete": "Só uma fonte", "materia": "Corpo", "fontes": ["https://unica.com"]})
        assert r.status_code == 200, r.text
        assert r.json()["fontes"] == ["https://unica.com"]
        assert r.json()["link"] == "https://unica.com"

    def test_reusa_a_mesma_fonte_blog_entre_publicacoes(self, client):
        c, engine = client
        c.post("/news/materias", json={"manchete": "A", "materia": "a", "fontes": []})
        c.post("/news/materias", json={"manchete": "B", "materia": "b", "fontes": []})
        with Session(engine) as s:
            fontes = s.exec(select(FonteNews).where(FonteNews.nome == "Blog CowData")).all()
            assert len(fontes) == 1

    def test_manchete_vazia_da_erro(self, client):
        c, _ = client
        r = c.post("/news/materias", json={"manchete": "  ", "materia": "Corpo", "fontes": []})
        assert r.status_code == 400

    def test_materia_vazia_da_erro(self, client):
        c, _ = client
        r = c.post("/news/materias", json={"manchete": "Título", "materia": "   ", "fontes": []})
        assert r.status_code == 400

    def test_operador_nao_pode_publicar(self, client_operador):
        c, _ = client_operador
        r = c.post("/news/materias", json={"manchete": "X", "materia": "Y", "fontes": []})
        assert r.status_code == 403

    def test_admin_sem_permissao_nao_pode_publicar_nem_excluir(self, client_admin_sem_permissao_publicar):
        """A permissão pode_publicar_materias_blog é independente de papel —
        um admin comum sem a flag também recebe 403 (igual exigir_dono)."""
        c, _ = client_admin_sem_permissao_publicar
        r = c.post("/news/materias", json={"manchete": "X", "materia": "Y", "fontes": []})
        assert r.status_code == 403
        r = c.delete("/news/materias/1")
        assert r.status_code == 403

    def test_excluir_materia(self, client):
        c, engine = client
        r = c.post("/news/materias", json={"manchete": "Para excluir", "materia": "Corpo", "fontes": []})
        nid = r.json()["id"]

        r = c.delete(f"/news/materias/{nid}")
        assert r.status_code == 200, r.text
        assert r.json()["excluido"] is True

        with Session(engine) as s:
            assert s.get(NoticiaNews, nid) is None

    def test_excluir_materia_inexistente_da_404(self, client):
        c, _ = client
        r = c.delete("/news/materias/999")
        assert r.status_code == 404

    def test_operador_nao_pode_excluir(self, client_operador):
        c, _ = client_operador
        r = c.delete("/news/materias/1")
        assert r.status_code == 403

    def test_materia_aparece_na_listagem(self, client, monkeypatch):
        c, _ = client
        monkeypatch.setattr("fazenda.api.routers.news.buscar_noticias_fonte", lambda url: [])
        c.post("/news/materias", json={"manchete": "Visível na listagem", "materia": "Corpo", "fontes": ["https://x.com"]})
        r = c.get("/news/")
        assert r.status_code == 200, r.text
        fonte = next(f for f in r.json()["fontes"] if f["fonte"]["nome"] == "Blog CowData")
        assert len(fonte["noticias"]) == 1
        assert fonte["noticias"][0]["manchete"] == "Visível na listagem"
        assert fonte["noticias"][0]["fontes"] == ["https://x.com"]


class TestRevisaoPublicacaoFinal:
    """POST /news/materias/{id}/revisar-final — aba própria em Configurações >
    News > "Revisão de publicação definitiva". Vale para qualquer matéria já
    publicada (robô /milknews, "Adicionar matéria ao blog" ou aprovação de
    pendente) — todas nascem com revisado_final=False; exige a permissão
    pode_publicar_materias_blog, e é sempre uma ação humana (o robô nunca
    chama este endpoint)."""

    def test_confirma_revisao_de_materia_do_blog(self, client):
        c, engine = client
        r = c.post("/news/materias", json={"manchete": "A revisar", "materia": "Corpo", "fontes": []})
        nid = r.json()["id"]
        assert r.json()["revisado_final"] is False

        r = c.post(f"/news/materias/{nid}/revisar-final")
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["revisado_final"] is True
        assert dados["revisado_final_por"] == "admin_teste"
        assert dados["revisado_final_em"] is not None

        with Session(engine) as s:
            noticia = s.get(NoticiaNews, nid)
            assert noticia.revisado_final is True
            assert noticia.revisado_final_por == "admin_teste"

    def test_confirma_revisao_de_materia_aprovada_do_robo(self, client):
        c, engine = client
        c.post("/news/manual", json={"itens": [
            {"fonte_nome": "MilkNews Diário", "manchete": "Preço do leite sobe", "link": "https://milknews.example.com/1"},
        ]})
        pend_id = c.get("/aprovacoes").json()[0]["id"]
        c.post(f"/aprovacoes/{pend_id}/aprovar")
        with Session(engine) as s:
            noticia = s.exec(select(NoticiaNews).where(NoticiaNews.link == "https://milknews.example.com/1")).first()
            assert noticia.revisado_final is False
            nid = noticia.id

        r = c.post(f"/news/materias/{nid}/revisar-final")
        assert r.status_code == 200, r.text
        assert r.json()["revisado_final"] is True

    def test_revisar_materia_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/news/materias/999/revisar-final")
        assert r.status_code == 404

    def test_operador_nao_pode_revisar(self, client_operador):
        c, _ = client_operador
        r = c.post("/news/materias/1/revisar-final")
        assert r.status_code == 403

    def test_admin_sem_permissao_nao_pode_revisar(self, client_admin_sem_permissao_publicar):
        c, _ = client_admin_sem_permissao_publicar
        r = c.post("/news/materias/1/revisar-final")
        assert r.status_code == 403


class TestPublicarLotesMilknews:
    """publicar_lotes_milknews() — seed de startup que publica cada lote de
    MILKNEWS_LOTES como matérias já aprovadas (sem fila de aprovação), sob a
    fonte manual "robô Milknews". Cada lote roda uma única vez (SeedFlag)."""

    def test_publica_lote_novo_sob_fonte_robo_milknews(self, client, monkeypatch):
        from fazenda.api.routers import news as news_module

        c, engine = client
        lotes = {
            "milknews_20260720": [{
                "manchete": "Preço do leite sobe no Cepea/Esalq",
                "resumo": "Cotação em alta na última semana. Dados: Cepea/Esalq (18/07/2026).",
                "link": "/news#milknews-2026-07-20-01",
                "data_publicacao": "2026-07-20",
            }],
        }
        monkeypatch.setattr(news_module, "MILKNEWS_LOTES", lotes)

        with Session(engine) as s:
            news_module.publicar_lotes_milknews(s)

        with Session(engine) as s:
            fonte = s.exec(select(FonteNews).where(FonteNews.nome == "robô Milknews")).first()
            assert fonte is not None and fonte.manual is True
            noticia = s.exec(select(NoticiaNews).where(NoticiaNews.link == "/news#milknews-2026-07-20-01")).first()
            assert noticia is not None
            assert noticia.manchete == "Preço do leite sobe no Cepea/Esalq"
            assert noticia.revisado_final is False
            assert noticia.data_publicacao == datetime(2026, 7, 20)

    def test_nao_republica_o_mesmo_lote_duas_vezes(self, client, monkeypatch):
        from fazenda.api.routers import news as news_module

        c, engine = client
        lotes = {
            "milknews_20260720": [{
                "manchete": "Matéria única do lote", "resumo": "Resumo.",
                "link": "/news#milknews-2026-07-20-01", "data_publicacao": "2026-07-20",
            }],
        }
        monkeypatch.setattr(news_module, "MILKNEWS_LOTES", lotes)

        with Session(engine) as s:
            news_module.publicar_lotes_milknews(s)

        # Mesmo que o lote mude de conteúdo depois, já rodou uma vez — nunca reaplica.
        lotes["milknews_20260720"][0]["manchete"] = "Manchete alterada"
        with Session(engine) as s:
            news_module.publicar_lotes_milknews(s)

        with Session(engine) as s:
            todas = s.exec(select(NoticiaNews)).all()
            assert len(todas) == 1
            assert todas[0].manchete == "Matéria única do lote"

    def test_backfill_preenche_fontes_de_materia_ja_publicada(self, client, monkeypatch):
        """Se o lote já publicado ganhar `fontes` depois (edição do dict), a
        próxima chamada preenche o campo na matéria existente sem reaplicar
        o lote nem alterar mais nada."""
        from fazenda.api.routers import news as news_module

        c, engine = client
        lotes = {
            "milknews_20260720": [{
                "manchete": "Matéria sem fontes ainda", "resumo": "Resumo.",
                "link": "/news#milknews-2026-07-20-01", "data_publicacao": "2026-07-20",
            }],
        }
        monkeypatch.setattr(news_module, "MILKNEWS_LOTES", lotes)
        with Session(engine) as s:
            news_module.publicar_lotes_milknews(s)

        lotes["milknews_20260720"][0]["fontes"] = ["https://cepea.esalq.usp.br/br/indicador/leite.aspx"]
        with Session(engine) as s:
            news_module.publicar_lotes_milknews(s)

        with Session(engine) as s:
            noticia = s.exec(select(NoticiaNews).where(NoticiaNews.link == "/news#milknews-2026-07-20-01")).first()
            assert noticia.manchete == "Matéria sem fontes ainda"
            assert json.loads(noticia.fontes) == ["https://cepea.esalq.usp.br/br/indicador/leite.aspx"]

    def test_backfill_nao_sobrescreve_fontes_ja_preenchidas(self, client, monkeypatch):
        """Se a matéria já tem `fontes` (preenchida manualmente ou por um
        backfill anterior), rodar de novo não troca o valor já salvo."""
        from fazenda.api.routers import news as news_module

        c, engine = client
        lotes = {
            "milknews_20260720": [{
                "manchete": "Matéria", "resumo": "Resumo.",
                "link": "/news#milknews-2026-07-20-01", "data_publicacao": "2026-07-20",
                "fontes": ["https://fonte-original.example.com"],
            }],
        }
        monkeypatch.setattr(news_module, "MILKNEWS_LOTES", lotes)
        with Session(engine) as s:
            news_module.publicar_lotes_milknews(s)

        lotes["milknews_20260720"][0]["fontes"] = ["https://fonte-diferente.example.com"]
        with Session(engine) as s:
            news_module.publicar_lotes_milknews(s)

        with Session(engine) as s:
            noticia = s.exec(select(NoticiaNews).where(NoticiaNews.link == "/news#milknews-2026-07-20-01")).first()
            assert json.loads(noticia.fontes) == ["https://fonte-original.example.com"]
