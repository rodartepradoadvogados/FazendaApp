"""
Testes do Portal (Administração > Portal > Comunicação): enviar mensagem
(com/sem pedido de retorno), enviar e-mail (livre ou relatório em anexo, com
Resend mockado) e delegar tarefa (permissão por tipo).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import AgendaManual, Pessoa, PortalMensagem, Usuario


@pytest.fixture
def ambiente():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        pessoa_vet = Pessoa(nome="Dra. Ana", tipo="Veterinário")
        pessoa_func = Pessoa(nome="João Funcionário", tipo="Funcionário")
        s.add(pessoa_vet)
        s.add(pessoa_func)
        s.commit()
        s.refresh(pessoa_vet)
        s.refresh(pessoa_func)

        s.add(Usuario(username="admin-teste", nome="Admin", senha_hash="x", papel="admin", ativo=True, email="admin@fazenda.com"))
        s.add(Usuario(username="vet-teste", nome="Veterinária", senha_hash="x", papel="operador", permissoes="", ativo=True, pessoa_id=pessoa_vet.id))
        s.add(Usuario(username="func-teste", nome="Funcionário", senha_hash="x", papel="operador", permissoes="", ativo=True, pessoa_id=pessoa_func.id))
        s.add(Usuario(username="robo-milknews", nome="Robô", senha_hash="x", papel="operador", permissoes="", ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _get_session_override
    yield main.app, engine
    main.app.dependency_overrides.clear()


def _client_como(app, engine, username):
    from fazenda.auth import get_current_user

    def _override(session: Session = Depends(database.get_session)):
        return session.exec(select(Usuario).where(Usuario.username == username)).first()

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


def _id_de(engine, username) -> int:
    with Session(engine) as s:
        return s.exec(select(Usuario).where(Usuario.username == username)).first().id


class TestDestinatarios:
    def test_lista_todos_menos_robo(self, ambiente):
        app, engine = ambiente
        c = _client_como(app, engine, "admin-teste")
        r = c.get("/portal/destinatarios")
        assert r.status_code == 200
        usernames = {u["username"] for u in r.json()}
        assert "robo-milknews" not in usernames
        assert "admin-teste" in usernames
        assert "vet-teste" in usernames


class TestEnviarMensagem:
    def test_mensagem_sem_pedir_retorno_some_ao_ler(self, ambiente):
        app, engine = ambiente
        remetente = _client_como(app, engine, "admin-teste")
        dest_id = _id_de(engine, "vet-teste")

        r = remetente.post("/portal/mensagens", json={
            "destinatarios_usuario_id": [dest_id], "corpo": "Bom dia", "pede_retorno": False,
        })
        assert r.status_code == 200
        assert r.json()["criadas"] == 1

        destinatario = _client_como(app, engine, "vet-teste")
        r = destinatario.get("/portal/mensagens/pendentes")
        assert len(r.json()) == 1
        msg_id = r.json()[0]["id"]

        r = destinatario.post(f"/portal/mensagens/{msg_id}/marcar-lida")
        assert r.status_code == 200

        r = destinatario.get("/portal/mensagens/pendentes")
        assert r.json() == []

    def test_mensagem_com_pedido_de_retorno_so_some_ao_resolver(self, ambiente):
        app, engine = ambiente
        remetente = _client_como(app, engine, "admin-teste")
        dest_id = _id_de(engine, "vet-teste")

        remetente.post("/portal/mensagens", json={
            "destinatarios_usuario_id": [dest_id], "corpo": "Preciso de retorno", "pede_retorno": True, "aba": "sanidade",
        })

        destinatario = _client_como(app, engine, "vet-teste")
        msg_id = destinatario.get("/portal/mensagens/pendentes").json()[0]["id"]

        destinatario.post(f"/portal/mensagens/{msg_id}/marcar-lida")
        # Lida mas com pedido de retorno — continua pendente.
        assert len(destinatario.get("/portal/mensagens/pendentes").json()) == 1

        destinatario.post(f"/portal/mensagens/{msg_id}/resolver")
        assert destinatario.get("/portal/mensagens/pendentes").json() == []

    def test_responder_resolve_original_e_notifica_remetente(self, ambiente):
        app, engine = ambiente
        remetente = _client_como(app, engine, "admin-teste")
        dest_id = _id_de(engine, "vet-teste")

        remetente.post("/portal/mensagens", json={
            "destinatarios_usuario_id": [dest_id], "corpo": "Confirma?", "pede_retorno": True,
        })

        destinatario = _client_como(app, engine, "vet-teste")
        msg_id = destinatario.get("/portal/mensagens/pendentes").json()[0]["id"]
        r = destinatario.post(f"/portal/mensagens/{msg_id}/responder", json={"corpo": "Confirmado"})
        assert r.status_code == 200

        assert destinatario.get("/portal/mensagens/pendentes").json() == []

        with Session(engine) as s:
            resposta = s.exec(select(PortalMensagem).where(PortalMensagem.resposta_de_id == msg_id)).first()
            assert resposta is not None
            assert resposta.destinatario_usuario_id == _id_de(engine, "admin-teste")

    def test_aba_invalida_rejeitada(self, ambiente):
        app, engine = ambiente
        remetente = _client_como(app, engine, "admin-teste")
        dest_id = _id_de(engine, "vet-teste")
        r = remetente.post("/portal/mensagens", json={
            "destinatarios_usuario_id": [dest_id], "corpo": "x", "aba": "sanidade-preventiva",
        })
        assert r.status_code == 400


class TestDelegarTarefa:
    def test_admin_pode_delegar(self, ambiente):
        app, engine = ambiente
        admin = _client_como(app, engine, "admin-teste")
        dest_id = _id_de(engine, "func-teste")
        r = admin.post("/portal/tarefas", json={"destinatarios_usuario_id": [dest_id], "corpo": "Verificar cerca"})
        assert r.status_code == 200
        assert r.json()["criadas"] == 1

        with Session(engine) as s:
            eventos = s.exec(select(AgendaManual)).all()
            assert len(eventos) == 1
            assert "Verificar cerca" in eventos[0].descricao

        destinatario = _client_como(app, engine, "func-teste")
        assert len(destinatario.get("/portal/mensagens/pendentes").json()) == 1

    def test_veterinario_pode_delegar(self, ambiente):
        app, engine = ambiente
        vet = _client_como(app, engine, "vet-teste")
        dest_id = _id_de(engine, "func-teste")
        r = vet.post("/portal/tarefas", json={"destinatarios_usuario_id": [dest_id], "corpo": "Aplicar vacina"})
        assert r.status_code == 200

    def test_funcionario_nao_pode_delegar(self, ambiente):
        app, engine = ambiente
        func = _client_como(app, engine, "func-teste")
        dest_id = _id_de(engine, "vet-teste")
        r = func.post("/portal/tarefas", json={"destinatarios_usuario_id": [dest_id], "corpo": "Teste"})
        assert r.status_code == 403


class TestEnviarEmail:
    def test_email_livre_para_si_proprio(self, ambiente, monkeypatch):
        app, engine = ambiente
        from fazenda.api.routers import portal as portal_router
        chamadas = []
        monkeypatch.setattr(
            portal_router, "enviar_email",
            lambda destinatario, assunto, corpo_html, anexo_nome=None, anexo_bytes=None: chamadas.append((destinatario, anexo_nome)),
        )
        admin = _client_como(app, engine, "admin-teste")
        admin_id = _id_de(engine, "admin-teste")
        r = admin.post("/portal/email", json={
            "destinatarios_usuario_id": [admin_id], "assunto": "Lembrete", "corpo": "Não esqueça",
        })
        assert r.status_code == 200
        assert r.json()["enviados"] == 1
        assert chamadas == [("admin@fazenda.com", None)]

    def test_email_sem_endereco_cadastrado_da_erro(self, ambiente, monkeypatch):
        app, engine = ambiente
        from fazenda.api.routers import portal as portal_router
        monkeypatch.setattr(portal_router, "enviar_email", lambda *a, **k: None)
        admin = _client_como(app, engine, "admin-teste")
        dest_id = _id_de(engine, "vet-teste")  # sem e-mail cadastrado
        r = admin.post("/portal/email", json={
            "destinatarios_usuario_id": [dest_id], "assunto": "Oi", "corpo": "Oi",
        })
        assert r.status_code == 400

    def test_email_com_relatorio_anexa_csv(self, ambiente, monkeypatch):
        app, engine = ambiente
        from fazenda.api.routers import portal as portal_router
        chamadas = []
        monkeypatch.setattr(
            portal_router, "enviar_email",
            lambda destinatario, assunto, corpo_html, anexo_nome=None, anexo_bytes=None: chamadas.append((anexo_nome, anexo_bytes)),
        )
        admin = _client_como(app, engine, "admin-teste")
        admin_id = _id_de(engine, "admin-teste")
        r = admin.post("/portal/email", json={
            "destinatarios_usuario_id": [admin_id], "assunto": "DRE", "relatorio": "dre",
            "data_inicio": "2026-01-01", "data_fim": "2026-01-31",
        })
        assert r.status_code == 200
        anexo_nome, anexo_bytes = chamadas[0]
        assert anexo_nome == "dre_2026-01-01_2026-01-31.csv"
        assert anexo_bytes and b"periodo" in anexo_bytes

    def test_relatorio_invalido_rejeitado(self, ambiente, monkeypatch):
        app, engine = ambiente
        from fazenda.api.routers import portal as portal_router
        monkeypatch.setattr(portal_router, "enviar_email", lambda *a, **k: None)
        admin = _client_como(app, engine, "admin-teste")
        admin_id = _id_de(engine, "admin-teste")
        r = admin.post("/portal/email", json={
            "destinatarios_usuario_id": [admin_id], "assunto": "x", "relatorio": "inexistente",
            "data_inicio": "2026-01-01", "data_fim": "2026-01-31",
        })
        assert r.status_code == 400
