"""
Banco de fotos do Milknews (fotos_news.py) — exclusão de foto.

MESMO defeito que já foi corrigido em documentos.py::excluir_documento e em
fotos.py::excluir_foto (relato do dono em 06/09/2026) e que continuava
intacto aqui: a falha do Supabase Storage virava 400 ANTES do
`session.delete`, então uma foto cujo arquivo já não existia no bucket
ficava presa para sempre na tela de Aprovações — toda tentativa repetia o
mesmo 400, justamente porque a causa era o arquivo não existir mais.

Cada teste nasceu reproduzindo a falha contra o código de então. O Storage é
sempre um dublê: `balde` é um dicionário, e apagar um caminho que não está
lá levanta RuntimeError EXATAMENTE como `excluir_arquivo` levanta quando o
Supabase responde 404 (ver rules/supabase_storage.py).

Atenção ao recorte: FotoNews é um banco GLOBAL e público (sem `fazenda_id` —
ver models/fotos_news.py e o docstring do router), então aqui não existe
recorte por fazenda a fazer dentro da consulta. Quem separa o que cada um
alcança é a permissão `exigir_pode_publicar`, e é ela que os testes de
isolamento abaixo cobrem, com contraprova de quem TEM a permissão.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO
from fazenda.models import FotoNews


class _QuedaAntesDoCommit(Exception):
    """Dublê da queda entre apagar o arquivo e gravar o commit — o que
    interessa é que a requisição morre DEPOIS do Storage e ANTES do commit,
    então a linha continua no banco."""


class _FakeEditorNews:
    """Tem a permissão de publicar matérias (e não é da Equipe CowData, por
    isso `pessoa_id = None` — ver exigir_pode_publicar)."""
    id = 1
    papel = "admin"
    ativo = True
    username = "editor_news"
    email = EMAIL_DONO
    pode_publicar_materias_blog = True
    pessoa_id = None


class _FakeAdminSemPermissao:
    """Admin comum SEM `pode_publicar_materias_blog` — a permissão é
    independente de papel/admin."""
    id = 2
    papel = "admin"
    ativo = True
    username = "admin_comum"
    email = "admin_comum@example.com"
    pode_publicar_materias_blog = False
    pessoa_id = None


def _montar(usuario, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: usuario()

    import fazenda.api.routers.fotos_news as fotos_news_mod

    balde: dict[str, bytes] = {}

    def _excluir(caminho, *a, **k):
        if caminho not in balde:
            raise RuntimeError("Falha ao excluir arquivo do Supabase Storage: 404 {'error':'not_found'}")
        balde.pop(caminho)

    monkeypatch.setattr(fotos_news_mod, "excluir_arquivo", _excluir)
    return main, engine, balde


@pytest.fixture
def ambiente(monkeypatch):
    main, engine, balde = _montar(_FakeEditorNews, monkeypatch)
    with TestClient(main.app) as c:
        yield c, engine, balde
    main.app.dependency_overrides.clear()


@pytest.fixture
def ambiente_sem_permissao(monkeypatch):
    main, engine, balde = _montar(_FakeAdminSemPermissao, monkeypatch)
    with TestClient(main.app) as c:
        yield c, engine, balde
    main.app.dependency_overrides.clear()


def _criar_foto(engine, balde, caminho: str, *, no_bucket: bool = True) -> int:
    with Session(engine) as s:
        foto = FotoNews(
            nome_arquivo="vaca.jpg", caminho_storage=caminho,
            mime_type="image/jpeg", tamanho_bytes=3, enviado_por=1,
        )
        s.add(foto)
        s.commit()
        s.refresh(foto)
        foto_id = foto.id
    if no_bucket:
        balde[caminho] = b"jpg"
    return foto_id


def _existe(engine, foto_id: int) -> bool:
    with Session(engine) as s:
        return s.exec(select(FotoNews).where(FotoNews.id == foto_id)).first() is not None


class TestExclusaoFotoNews:
    def test_exclusao_normal_apaga_arquivo_e_linha(self, ambiente):
        client, engine, balde = ambiente
        foto_id = _criar_foto(engine, balde, "abc_vaca.jpg")

        r = client.delete(f"/fotos-news/{foto_id}")

        assert r.status_code == 200, r.text
        assert r.json() == {"excluido": True}
        assert "abc_vaca.jpg" not in balde  # o objeto saiu mesmo do bucket
        assert not _existe(engine, foto_id)

    def test_arquivo_ja_inexistente_nao_trava_a_exclusao(self, ambiente):
        """Apagado à mão no painel do Supabase, ou upload que falhou no meio:
        apagar o registro cujo arquivo já sumiu é exatamente o que o usuário
        quer — antes isto devolvia 400 para sempre."""
        client, engine, balde = ambiente
        foto_id = _criar_foto(engine, balde, "abc_fantasma.jpg", no_bucket=False)

        r = client.delete(f"/fotos-news/{foto_id}")

        assert r.status_code == 200, r.text
        assert not _existe(engine, foto_id)

    def test_falha_generica_do_storage_nao_segura_a_linha(self, ambiente, monkeypatch):
        """Storage fora do ar (500), não só 404: a linha é o que o usuário
        enxerga e é ela que tem que sair; no pior caso sobra um objeto órfão
        no bucket, invisível, sem nenhuma linha apontando."""
        client, engine, balde = ambiente
        foto_id = _criar_foto(engine, balde, "abc_instavel.jpg")

        import fazenda.api.routers.fotos_news as fotos_news_mod

        def _explode(*a, **k):
            raise RuntimeError("Falha ao excluir arquivo do Supabase Storage: 500 {'error':'internal'}")

        monkeypatch.setattr(fotos_news_mod, "excluir_arquivo", _explode)

        r = client.delete(f"/fotos-news/{foto_id}")

        assert r.status_code == 200, r.text
        assert not _existe(engine, foto_id)

    def test_segunda_tentativa_depois_do_arquivo_sumir_termina_o_servico(self, ambiente, monkeypatch):
        """A pergunta do commit: arquivo apagado e commit falhando depois. A
        linha continua no banco; na tentativa seguinte o Storage responde 404
        (agora tolerado) e a linha sai — o estado converge sozinho."""
        client, engine, balde = ambiente
        foto_id = _criar_foto(engine, balde, "abc_meio_caminho.jpg")

        import fazenda.api.routers.fotos_news as fotos_news_mod

        excluir_real = fotos_news_mod.excluir_arquivo

        def _apaga_e_derruba_o_commit(caminho, *a, **k):
            excluir_real(caminho, *a, **k)  # o objeto SAI do bucket
            raise _QuedaAntesDoCommit("banco fora do ar na hora do commit")

        monkeypatch.setattr(fotos_news_mod, "excluir_arquivo", _apaga_e_derruba_o_commit)
        with pytest.raises(_QuedaAntesDoCommit):
            client.delete(f"/fotos-news/{foto_id}")

        assert "abc_meio_caminho.jpg" not in balde
        assert _existe(engine, foto_id)  # linha sobreviveu, como esperado

        monkeypatch.setattr(fotos_news_mod, "excluir_arquivo", excluir_real)
        r = client.delete(f"/fotos-news/{foto_id}")

        assert r.status_code == 200, r.text
        assert not _existe(engine, foto_id)

    def test_foto_inexistente_404(self, ambiente):
        client, _engine, _balde = ambiente
        assert client.delete("/fotos-news/9999").status_code == 404


class TestIsolamentoFotoNews:
    """FotoNews não tem `fazenda_id` — o banco de fotos é global e público
    (uma foto ilustra a matéria do blog, que é a mesma para todo mundo).
    Não há recorte de fazenda a aplicar na consulta; o que separa quem
    alcança o quê é `exigir_pode_publicar`, e é isso que se testa aqui,
    junto da contraprova de quem TEM a permissão."""

    def test_modelo_nao_tem_fazenda_id(self):
        assert "fazenda_id" not in FotoNews.model_fields

    def test_sem_permissao_de_publicar_nao_exclui_e_a_linha_fica(self, ambiente_sem_permissao):
        client, engine, balde = ambiente_sem_permissao
        foto_id = _criar_foto(engine, balde, "abc_alheia.jpg")

        r = client.delete(f"/fotos-news/{foto_id}")

        assert r.status_code == 403
        assert "abc_alheia.jpg" in balde
        assert _existe(engine, foto_id)

    def test_contraprova_com_permissao_exclui(self, ambiente):
        client, engine, balde = ambiente
        foto_id = _criar_foto(engine, balde, "abc_permitida.jpg")

        assert client.delete(f"/fotos-news/{foto_id}").status_code == 200
        assert not _existe(engine, foto_id)
