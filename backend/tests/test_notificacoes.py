"""
Testes do sininho de notificações: agrega eventos de hoje + pendências de
exclusão, filtrando por módulo/permissão do usuário logado.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import AgendaManual, PortalMensagem, SolicitacaoExclusao, Usuario


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


class _FakeOperadorSoAgenda:
    id = 2
    papel = "operador"
    permissoes = "agenda"
    ativo = True
    username = "operador_agenda"


class _FakeOperadorSemNada:
    id = 3
    papel = "operador"
    permissoes = ""
    ativo = True
    username = "operador_vazio"


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with Session(engine) as s:
        s.add(AgendaManual(data_evento=date.today(), descricao="Reunião com veterinário", categoria="Atividades"))
        s.add(SolicitacaoExclusao(tipo="animal", id_alvo="1", titulo="Ficha do animal 1", solicitado_por="fulano"))
        s.add(Usuario(id=1, username="admin_teste", senha_hash="x", papel="admin", ativo=True))
        s.add(Usuario(id=50, username="peao.teste", nome="Peão Teste", senha_hash="x", papel="operador", ativo=True))
        s.add(PortalMensagem(
            tipo="foto", remetente_usuario_id=50, destinatario_usuario_id=1,
            corpo="14:32 — Animal 123: Machucado na pata", foto_campo_id=None,
        ))
        s.commit()

    yield main.app
    main.app.dependency_overrides.clear()


def _client_as(app, user):
    from fazenda.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestNotificacoes:
    def test_admin_ve_evento_de_hoje_e_pendencia_de_exclusao(self, setup):
        c = _client_as(setup, _FakeAdmin())
        r = c.get("/notificacoes/")
        assert r.status_code == 200
        d = r.json()
        tipos = {i["tipo"] for i in d["itens"]}
        assert "agenda" in tipos
        assert "exclusao_pendente" in tipos
        assert d["total"] == len(d["itens"])

    def test_operador_sem_permissao_nao_ve_exclusao_pendente(self, setup):
        c = _client_as(setup, _FakeOperadorSoAgenda())
        r = c.get("/notificacoes/")
        tipos = {i["tipo"] for i in r.json()["itens"]}
        assert "exclusao_pendente" not in tipos

    def test_operador_com_modulo_agenda_ve_evento_atividades(self, setup):
        c = _client_as(setup, _FakeOperadorSoAgenda())
        r = c.get("/notificacoes/")
        categorias = {i["categoria"] for i in r.json()["itens"]}
        assert "Atividades" in categorias

    def test_operador_sem_nenhum_modulo_nao_ve_nada(self, setup):
        c = _client_as(setup, _FakeOperadorSemNada())
        r = c.get("/notificacoes/")
        assert r.json()["itens"] == []
        assert r.json()["total"] == 0

    def test_admin_ve_aviso_de_foto_do_campo(self, setup):
        c = _client_as(setup, _FakeAdmin())
        r = c.get("/notificacoes/")
        itens_foto = [i for i in r.json()["itens"] if i["tipo"] == "portal_mensagem" and i.get("descricao", "").startswith("Foto de")]
        assert len(itens_foto) == 1
        assert itens_foto[0]["descricao"] == "Foto de Peão Teste: 14:32 — Animal 123: Machucado na pata"

    def test_marcar_lida_remove_aviso_de_foto(self, setup):
        c = _client_as(setup, _FakeAdmin())
        r = c.get("/notificacoes/")
        item = next(i for i in r.json()["itens"] if i["tipo"] == "portal_mensagem")
        c.post(f"/portal/mensagens/{item['portal_mensagem_id']}/marcar-lida")
        r2 = c.get("/notificacoes/")
        assert not any(i["tipo"] == "portal_mensagem" for i in r2.json()["itens"])
