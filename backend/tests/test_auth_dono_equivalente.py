"""
Testes de fazenda.auth.EMAILS_DONO_EQUIVALENTE — o sócio Alexandre Scarpa
(alexandrescarpazoo@yahoo.com.br) recebe exatamente o mesmo acesso de
proprietário que EMAIL_DONO (Jairo), a pedido explícito do proprietário
("ele precisa exatamente do mesmo acesso que eu dentro do site"). O
mecanismo é aditivo: EMAIL_DONO continua funcionando sozinho (ver os demais
testes que já cobrem EMAIL_DONO isoladamente), e um terceiro e-mail qualquer
continua bloqueado.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, EMAILS_DONO_EQUIVALENTE, eh_email_dono_equivalente, hash_senha
from fazenda.models import Usuario

EMAIL_SOCIO = "alexandrescarpazoo@yahoo.com.br"


def test_email_socio_esta_na_lista_equivalente():
    assert EMAIL_SOCIO in EMAILS_DONO_EQUIVALENTE
    assert EMAIL_DONO in EMAILS_DONO_EQUIVALENTE


def test_eh_email_dono_equivalente_helper():
    assert eh_email_dono_equivalente(EMAIL_DONO) is True
    assert eh_email_dono_equivalente(EMAIL_SOCIO) is True
    assert eh_email_dono_equivalente(" " + EMAIL_SOCIO.upper() + " ") is True  # trim + case-insensitive
    assert eh_email_dono_equivalente("outro-admin@example.com") is False
    assert eh_email_dono_equivalente(None) is False


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.add(Usuario(username="socio", nome="Alexandre Scarpa", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_SOCIO))
        s.add(Usuario(username="outro-admin", nome="Outro", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _login(c, username):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_socio_recebe_eh_dono_true_no_auth_me(client):
    token = _login(client, "socio")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["eh_dono"] is True


def test_dono_original_continua_eh_dono_true(client):
    token = _login(client, "dono")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["eh_dono"] is True


def test_outro_admin_qualquer_continua_eh_dono_false(client):
    token = _login(client, "outro-admin")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["eh_dono"] is False


def test_socio_acessa_rota_exigir_dono(client):
    """exigir_dono-gated (relatório de Acessos — mesmo endpoint já coberto
    por test_auth_acessos.py para EMAIL_DONO sozinho). Painel CowData usa a
    mesma dependência (exigir_dono), então fica coberto pela mesma checagem —
    seu 500 sem a Fazenda interna da CowData provisionada é um pré-requisito
    de dados à parte, não de autorização."""
    token = _login(client, "socio")
    r = client.get("/auth/usuarios/acessos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_outro_admin_nao_acessa_rota_exigir_dono(client):
    token = _login(client, "outro-admin")
    r = client.get("/auth/usuarios/acessos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
