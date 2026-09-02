"""
PUT /auth/preferencias — qualquer usuário logado edita paleta/e-mail próprios
(ver fazenda.api.routers.auth.salvar_preferencias). É o único jeito
self-service de um administrador virar "dono" (eh_dono compara com
EMAIL_DONO — Controle de Acesso e Acessos e Auditoria dependem disso), então
tem duas travas: só admin pode reivindicar o e-mail do proprietário, e só
quando ninguém mais já é dono — senão qualquer usuário comum poderia se
autopromover digitando o e-mail certo.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, EMAILS_DONO_EQUIVALENTE, hash_senha
from fazenda.models import Usuario

EMAIL_SOCIO = next(e for e in EMAILS_DONO_EQUIVALENTE if e != EMAIL_DONO)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="admin_sem_email", nome="Admin", senha_hash=hash_senha("123"), papel="admin"))
        s.add(Usuario(username="operador", nome="Operador", senha_hash=hash_senha("123"), papel="operador"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _login(c, username):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_admin_reivindica_email_do_dono_quando_ninguem_e_dono(client):
    c, engine = client
    token = _login(c, "admin_sem_email")
    r = c.put("/auth/preferencias", json={"email": EMAIL_DONO}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["eh_dono"] is True
    with Session(engine) as s:
        admin = s.exec(select(Usuario).where(Usuario.username == "admin_sem_email")).first()
        assert admin.email == EMAIL_DONO


def test_operador_nao_pode_reivindicar_email_do_dono(client):
    c, _ = client
    token = _login(c, "operador")
    r = c.put("/auth/preferencias", json={"email": EMAIL_DONO}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_nao_pode_reivindicar_se_ja_existe_dono(client):
    c, engine = client
    with Session(engine) as s:
        s.add(Usuario(username="dono_atual", nome="Dono", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.commit()
    token = _login(c, "admin_sem_email")
    r = c.put("/auth/preferencias", json={"email": EMAIL_DONO}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_ja_dono_pode_resalvar_o_proprio_email_sem_erro(client):
    c, engine = client
    with Session(engine) as s:
        admin = s.exec(select(Usuario).where(Usuario.username == "admin_sem_email")).first()
        admin.email = EMAIL_DONO
        s.add(admin)
        s.commit()
    token = _login(c, "admin_sem_email")
    r = c.put("/auth/preferencias", json={"email": EMAIL_DONO}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


def test_qualquer_usuario_pode_setar_email_pessoal_qualquer(client):
    c, engine = client
    token = _login(c, "operador")
    r = c.put("/auth/preferencias", json={"email": "operador@fazenda.com"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["eh_dono"] is False
    with Session(engine) as s:
        op = s.exec(select(Usuario).where(Usuario.username == "operador")).first()
        assert op.email == "operador@fazenda.com"


def test_admin_reivindica_via_flag_sem_precisar_saber_o_email(client):
    """reivindicar_proprietario=True é o caminho preferido: o frontend nunca
    precisa conhecer/enviar o valor de EMAIL_DONO — evita o erro comum de um
    admin digitar o PRÓPRIO e-mail pessoal achando que é isso que o promove
    (aquele caminho só salva um contato comum e nunca vira dono)."""
    c, engine = client
    token = _login(c, "admin_sem_email")
    r = c.put("/auth/preferencias", json={"reivindicar_proprietario": True}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["eh_dono"] is True
    with Session(engine) as s:
        admin = s.exec(select(Usuario).where(Usuario.username == "admin_sem_email")).first()
        assert admin.email == EMAIL_DONO


def test_operador_nao_pode_reivindicar_via_flag(client):
    c, _ = client
    token = _login(c, "operador")
    r = c.put("/auth/preferencias", json={"reivindicar_proprietario": True}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_operador_nao_pode_se_autopromover_com_email_socio_equivalente(client):
    """Bug de segurança corrigido: a checagem antiga comparava só com
    EMAIL_DONO — qualquer usuário autenticado (mesmo operador) conseguia
    virar dono-equivalente enviando diretamente o e-mail do sócio
    (EMAIL_SOCIO, em EMAILS_DONO_EQUIVALENTE mas != EMAIL_DONO), pulando por
    inteiro as travas de exigir_admin e "só quando ninguém mais é dono"."""
    c, engine = client
    token = _login(c, "operador")
    r = c.put("/auth/preferencias", json={"email": EMAIL_SOCIO}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    with Session(engine) as s:
        op = s.exec(select(Usuario).where(Usuario.username == "operador")).first()
        assert op.email is None


def test_admin_nao_pode_setar_proprio_email_como_o_do_socio_equivalente(client):
    """Nem mesmo um admin pode assumir EMAIL_SOCIO por aqui — o único
    e-mail dono-equivalente auto-atendível é o literal EMAIL_DONO (via
    reivindicar_proprietario ou digitando o valor certo)."""
    c, engine = client
    token = _login(c, "admin_sem_email")
    r = c.put("/auth/preferencias", json={"email": EMAIL_SOCIO}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    with Session(engine) as s:
        admin = s.exec(select(Usuario).where(Usuario.username == "admin_sem_email")).first()
        assert admin.email is None


def test_nao_pode_reivindicar_via_flag_se_ja_existe_dono(client):
    c, engine = client
    with Session(engine) as s:
        s.add(Usuario(username="dono_atual", nome="Dono", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.commit()
    token = _login(c, "admin_sem_email")
    r = c.put("/auth/preferencias", json={"reivindicar_proprietario": True}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
