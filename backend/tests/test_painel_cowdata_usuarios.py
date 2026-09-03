"""
Painel CowData > Usuários — cria/edita login de operadores de UMA fazenda-
cliente por vez, com fazenda_id explícito no path. Ver
fazenda/api/routers/painel_cowdata_usuarios.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, EMAILS_DONO_EQUIVALENTE, hash_senha
from fazenda.models import Fazenda, Pessoa, Usuario, UsuarioFazenda

EMAIL_SOCIO = next(e for e in EMAILS_DONO_EQUIVALENTE if e != EMAIL_DONO)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fa = Fazenda(nome="Fazenda A", ativa=True)
        fb = Fazenda(nome="Fazenda B", ativa=True)
        s.add_all([fa, fb])
        s.commit()
        s.refresh(fa)
        s.refresh(fb)
        fa_id, fb_id = fa.id, fb.id

        pessoa_a = Pessoa(nome="João da Fazenda A", tipo="Funcionário", email="joao@a.com", fazenda_id=fa_id)
        pessoa_b = Pessoa(nome="Maria da Fazenda B", tipo="Funcionário", fazenda_id=fb_id)
        s.add_all([pessoa_a, pessoa_b])
        s.commit()
        s.refresh(pessoa_a)
        s.refresh(pessoa_b)
        pessoa_a_id, pessoa_b_id = pessoa_a.id, pessoa_b.id

        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        comum = Usuario(username="admin-comum", nome="Admin comum", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com")
        s.add_all([dono, comum])
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id
    main.app.dependency_overrides.clear()


def _login(c, username="dono"):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_nao_dono_sem_area_e_bloqueado(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c, "admin-comum")
    r = c.get(f"/painel-cowdata/usuarios/{fa_id}/pessoas", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_listar_pessoas_so_da_fazenda_escolhida(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    r = c.get(f"/painel-cowdata/usuarios/{fa_id}/pessoas", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    nomes = {p["nome"] for p in r.json()}
    assert nomes == {"João da Fazenda A"}


def test_criar_usuario_operador_com_permissoes(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    r = c.post(
        f"/painel-cowdata/usuarios/{fa_id}",
        json={"pessoa_id": pessoa_a_id, "username": "joao.a", "senha": "senha123", "papel": "operador", "permissoes": ["rebanho", "agenda"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == "joao.a"
    assert set(body["permissoes"]) == {"rebanho", "agenda"}

    with Session(engine) as s:
        vinculo = s.exec(select(UsuarioFazenda).where(UsuarioFazenda.fazenda_id == fa_id)).first()
        assert vinculo is not None
        assert vinculo.contratante is False


def test_criar_usuario_admin_cria_vinculo_contratante(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    r = c.post(
        f"/painel-cowdata/usuarios/{fa_id}",
        json={"pessoa_id": pessoa_a_id, "username": "joao.admin", "senha": "senha123", "papel": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        vinculo = s.exec(select(UsuarioFazenda).where(UsuarioFazenda.fazenda_id == fa_id)).first()
        assert vinculo.contratante is True


def test_pessoa_de_outra_fazenda_e_rejeitada(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    r = c.post(
        f"/painel-cowdata/usuarios/{fa_id}",
        json={"pessoa_id": pessoa_b_id, "username": "maria.b", "senha": "senha123", "papel": "operador"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_listar_usuarios_isola_por_fazenda(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    c.post(
        f"/painel-cowdata/usuarios/{fa_id}",
        json={"pessoa_id": pessoa_a_id, "username": "joao.a", "senha": "senha123", "papel": "operador"},
        headers={"Authorization": f"Bearer {token}"},
    )
    c.post(
        f"/painel-cowdata/usuarios/{fb_id}",
        json={"pessoa_id": pessoa_b_id, "username": "maria.b", "senha": "senha123", "papel": "operador"},
        headers={"Authorization": f"Bearer {token}"},
    )
    r = c.get(f"/painel-cowdata/usuarios/{fa_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    usernames = {u["username"] for u in r.json()}
    assert usernames == {"joao.a"}


def test_editar_usuario_reseta_senha_e_papel(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    r = c.post(
        f"/painel-cowdata/usuarios/{fa_id}",
        json={"pessoa_id": pessoa_a_id, "username": "joao.a", "senha": "senha123", "papel": "operador", "permissoes": ["rebanho"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    usuario_id = r.json()["id"]
    r = c.put(
        f"/painel-cowdata/usuarios/{fa_id}/{usuario_id}",
        json={"papel": "admin", "senha": "novaSenha"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["papel"] == "admin"
    with Session(engine) as s:
        vinculo = s.exec(select(UsuarioFazenda).where(UsuarioFazenda.fazenda_id == fa_id)).first()
        assert vinculo.contratante is True

    r = c.post("/auth/login", json={"username": "joao.a", "senha": "novaSenha"})
    assert r.status_code == 200


def test_criar_usuario_com_email_dono_equivalente_e_rejeitado(client):
    """Bug de segurança corrigido: esta rota é gated só por
    exigir_area_painel_cowdata("cadastros") (área de baixo privilégio, não
    exigir_dono) — sem esta trava, um operador do CowData com acesso a
    "cadastros" conseguia criar um usuário de uma fazenda-cliente com o
    e-mail dono-equivalente e depois escalar privilégio via
    PUT /auth/preferencias digitando o mesmo e-mail (== self-service, sem
    nenhuma trava de admin/duplicidade nesse segundo passo)."""
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    r = c.post(
        f"/painel-cowdata/usuarios/{fa_id}",
        json={"pessoa_id": pessoa_a_id, "username": "joao.a", "senha": "senha123", "papel": "operador", "email": EMAIL_SOCIO},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    with Session(engine) as s:
        assert s.exec(select(Usuario).where(Usuario.username == "joao.a")).first() is None


def test_editar_usuario_com_email_dono_equivalente_e_rejeitado(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    r = c.post(
        f"/painel-cowdata/usuarios/{fa_id}",
        json={"pessoa_id": pessoa_a_id, "username": "joao.a", "senha": "senha123", "papel": "operador"},
        headers={"Authorization": f"Bearer {token}"},
    )
    usuario_id = r.json()["id"]
    r = c.put(
        f"/painel-cowdata/usuarios/{fa_id}/{usuario_id}",
        json={"email": EMAIL_SOCIO},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    with Session(engine) as s:
        assert s.get(Usuario, usuario_id).email is None


def test_editar_usuario_de_outra_fazenda_e_rejeitado(client):
    c, engine, fa_id, fb_id, pessoa_a_id, pessoa_b_id = client
    token = _login(c)
    r = c.post(
        f"/painel-cowdata/usuarios/{fb_id}",
        json={"pessoa_id": pessoa_b_id, "username": "maria.b", "senha": "senha123", "papel": "operador"},
        headers={"Authorization": f"Bearer {token}"},
    )
    usuario_id = r.json()["id"]
    r = c.put(
        f"/painel-cowdata/usuarios/{fa_id}/{usuario_id}",
        json={"ativo": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
