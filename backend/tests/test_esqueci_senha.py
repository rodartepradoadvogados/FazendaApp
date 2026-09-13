"""
Testes do fluxo "Esqueci minha senha" (login/página pública):
1) verificar se o login existe (e devolver o e-mail mascarado)
2) enviar o e-mail de redefinição (token de uso único, válido por 1h)
3) redefinir a senha com o token
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import hash_senha, verificar_senha
from fazenda.models import Usuario


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="joao", nome="João", senha_hash=hash_senha("senha-antiga"), papel="operador",
                       email="joaosilva@example.com", ativo=True))
        s.add(Usuario(username="sememail", nome="Sem Email", senha_hash=hash_senha("123"), papel="operador", ativo=True))
        s.add(Usuario(username="inativo", nome="Inativo", senha_hash=hash_senha("123"), papel="operador",
                       email="inativo@example.com", ativo=False))
        # Nome com HTML: `Usuario.nome` é texto livre digitado por quem cadastra
        # (ver routers/auth.py::_validar_pessoa_ou_nome) e vai interpolado no
        # corpo do e-mail de redefinição — ver TestEscapeDoNome, no fim deste
        # arquivo.
        s.add(Usuario(username="xss", nome='<script>alert(1)</script>', senha_hash=hash_senha("123"),
                       papel="operador", email="xss@example.com", ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    enviados = []
    monkeypatch.setattr(
        "fazenda.api.routers.auth.enviar_email",
        lambda destinatario, assunto, corpo_html, anexo_nome=None, anexo_bytes=None: enviados.append(
            {"destinatario": destinatario, "assunto": assunto, "corpo_html": corpo_html}
        ),
    )

    with TestClient(main.app) as c:
        yield c, engine, enviados
    main.app.dependency_overrides.clear()


class TestVerificar:
    def test_login_existente_devolve_email_mascarado(self, client):
        c, engine, _ = client
        r = c.post("/auth/esqueci-senha/verificar", json={"username": "joao"})
        assert r.status_code == 200
        d = r.json()
        assert d["existe"] is True
        assert d["tem_email"] is True
        assert d["email_mascarado"] == "j***va@example.com"

    def test_login_inexistente_nao_expoe_nada(self, client):
        c, engine, _ = client
        r = c.post("/auth/esqueci-senha/verificar", json={"username": "naoexiste"})
        assert r.status_code == 200
        assert r.json() == {"existe": False}

    def test_login_inativo_tratado_como_inexistente(self, client):
        c, engine, _ = client
        r = c.post("/auth/esqueci-senha/verificar", json={"username": "inativo"})
        assert r.json() == {"existe": False}

    def test_login_sem_email_cadastrado(self, client):
        c, engine, _ = client
        r = c.post("/auth/esqueci-senha/verificar", json={"username": "sememail"})
        d = r.json()
        assert d["existe"] is True
        assert d["tem_email"] is False
        assert "email_mascarado" not in d


class TestEnviar:
    def test_envia_email_e_grava_token_com_expiracao(self, client):
        c, engine, enviados = client
        r = c.post("/auth/esqueci-senha/enviar", json={"username": "joao"})
        assert r.status_code == 200
        assert r.json() == {"enviado": True}
        assert len(enviados) == 1
        assert enviados[0]["destinatario"] == "joaosilva@example.com"

        with Session(engine) as s:
            user = s.exec(select(Usuario).where(Usuario.username == "joao")).first()
            assert user.reset_senha_token
            assert user.reset_senha_expira > datetime.utcnow()
            assert user.reset_senha_expira <= datetime.utcnow() + timedelta(hours=1, minutes=1)

    def test_recusa_enviar_para_usuario_sem_email(self, client):
        c, engine, enviados = client
        r = c.post("/auth/esqueci-senha/enviar", json={"username": "sememail"})
        assert r.status_code == 404
        assert not enviados

    def test_email_nao_configurado_vira_erro_tratado(self, client, monkeypatch):
        c, engine, _ = client

        def _sem_configuracao(*args, **kwargs):
            raise RuntimeError("Envio de e-mail não está configurado — falta a variável de ambiente RESEND_API_KEY.")

        monkeypatch.setattr("fazenda.api.routers.auth.enviar_email", _sem_configuracao)
        r = c.post("/auth/esqueci-senha/enviar", json={"username": "joao"})
        assert r.status_code == 503
        assert "RESEND_API_KEY" in r.json()["detail"]


class TestRedefinir:
    def test_redefine_com_token_valido(self, client):
        c, engine, _ = client
        c.post("/auth/esqueci-senha/enviar", json={"username": "joao"})
        with Session(engine) as s:
            token = s.exec(select(Usuario).where(Usuario.username == "joao")).first().reset_senha_token

        r = c.post("/auth/redefinir-senha", json={"token": token, "nova_senha": "senha-nova-123"})
        assert r.status_code == 200
        assert r.json() == {"redefinido": True}

        with Session(engine) as s:
            user = s.exec(select(Usuario).where(Usuario.username == "joao")).first()
            assert verificar_senha("senha-nova-123", user.senha_hash)
            assert user.reset_senha_token is None
            assert user.reset_senha_expira is None

        # login com a senha antiga já não funciona mais
        r2 = c.post("/auth/login", json={"username": "joao", "senha": "senha-antiga"})
        assert r2.status_code == 401
        r3 = c.post("/auth/login", json={"username": "joao", "senha": "senha-nova-123"})
        assert r3.status_code == 200

    def test_rejeita_token_invalido(self, client):
        c, engine, _ = client
        r = c.post("/auth/redefinir-senha", json={"token": "token-que-nao-existe", "nova_senha": "abc123"})
        assert r.status_code == 400

    def test_rejeita_token_expirado(self, client):
        c, engine, _ = client
        c.post("/auth/esqueci-senha/enviar", json={"username": "joao"})
        with Session(engine) as s:
            user = s.exec(select(Usuario).where(Usuario.username == "joao")).first()
            user.reset_senha_expira = datetime.utcnow() - timedelta(minutes=1)
            token = user.reset_senha_token
            s.add(user)
            s.commit()

        r = c.post("/auth/redefinir-senha", json={"token": token, "nova_senha": "abc123"})
        assert r.status_code == 400

    def test_rejeita_senha_curta_demais(self, client):
        c, engine, _ = client
        c.post("/auth/esqueci-senha/enviar", json={"username": "joao"})
        with Session(engine) as s:
            token = s.exec(select(Usuario).where(Usuario.username == "joao")).first().reset_senha_token
        r = c.post("/auth/redefinir-senha", json={"token": token, "nova_senha": "ab"})
        assert r.status_code == 400


class TestEscapeDoNome:
    """Achado de severidade baixa da auditoria de 02/09/2026
    (docs/security-audit/achados.json): `user.nome` ia cru para dentro do HTML
    do e-mail de redefinição.

    É majoritariamente self-XSS — o e-mail sai só para o endereço cadastrado da
    própria pessoa, e para explorá-lo alguém já teria que ter cadastrado um nome
    malicioso para ela. Mas o nome é texto livre, o destino é HTML, e "texto de
    usuário não escapado em HTML" não deixa de ser isso por o alvo ser
    inconveniente. O escape mora em `routers/auth.py::esqueci_senha_enviar`.
    """

    def test_nome_com_html_sai_escapado_no_corpo_do_email(self, client):
        c, _engine, enviados = client
        r = c.post("/auth/esqueci-senha/enviar", json={"username": "xss"})
        assert r.status_code == 200, r.text

        corpo = enviados[-1]["corpo_html"]
        assert "<script>" not in corpo, (
            "o nome do usuário entrou cru no HTML do e-mail — o cliente de e-mail que renderiza "
            f"HTML executaria isso. Corpo: {corpo[:300]}"
        )
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in corpo, (
            "o nome sumiu do e-mail em vez de aparecer escapado — escapar não é apagar; "
            f"a pessoa continua tendo que se reconhecer na mensagem. Corpo: {corpo[:300]}"
        )

    def test_o_link_de_redefinicao_continua_no_email(self, client):
        """Contraprova: o escape não pode ter estragado o e-mail. Sem o link,
        o fluxo inteiro morre e o teste de cima passaria assim mesmo."""
        c, engine, enviados = client
        c.post("/auth/esqueci-senha/enviar", json={"username": "xss"})
        with Session(engine) as s:
            token = s.exec(select(Usuario).where(Usuario.username == "xss")).first().reset_senha_token
        assert f"/redefinir-senha?token={token}" in enviados[-1]["corpo_html"]

    def test_nome_comum_nao_e_alterado(self, client):
        """Segunda contraprova: nome sem HTML nenhum sai idêntico — o escape
        não pode acentuar/deformar o nome de quem não fez nada."""
        c, _engine, enviados = client
        c.post("/auth/esqueci-senha/enviar", json={"username": "joao"})
        assert "Olá, João!" in enviados[-1]["corpo_html"]
