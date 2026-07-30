"""
"Manter conectado neste aparelho" (checkbox no login, marcada por padrão
dentro do app Capacitor) — POST /auth/login aceita `manter_conectado` e emite
um token de validade bem mais longa (TOKEN_VALIDADE_LONGA_S) em vez das 12h
padrão. POST /auth/selecionar-fazenda (piloto de multi-fazenda) precisa
preservar essa escolha ao reemitir o token já com a fazenda selecionada.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import TOKEN_VALIDADE_LONGA_S, TOKEN_VALIDADE_S, _validar_token_payload, hash_senha
from fazenda.models import Fazenda, Usuario, UsuarioFazenda


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="joao", nome="João", senha_hash=hash_senha("123"), papel="operador", ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def test_login_sem_manter_conectado_usa_validade_padrao(client):
    c, _ = client
    r = c.post("/auth/login", json={"username": "joao", "senha": "123"})
    assert r.status_code == 200
    payload = _validar_token_payload(r.json()["token"])
    assert "lembrar" not in payload
    # Validade de ~12h (com folga para o tempo de execução do teste).
    assert TOKEN_VALIDADE_S - 5 <= payload["exp"] - time.time() <= TOKEN_VALIDADE_S + 5


def test_login_com_manter_conectado_usa_validade_longa(client):
    c, _ = client
    r = c.post("/auth/login", json={"username": "joao", "senha": "123", "manter_conectado": True})
    assert r.status_code == 200
    payload = _validar_token_payload(r.json()["token"])
    assert payload["lembrar"] is True
    assert TOKEN_VALIDADE_LONGA_S - 5 <= payload["exp"] - time.time() <= TOKEN_VALIDADE_LONGA_S + 5


def test_selecionar_fazenda_preserva_manter_conectado(client):
    c, engine = client
    with Session(engine) as s:
        from sqlmodel import select
        f1 = Fazenda(nome="Fazenda 1")
        f2 = Fazenda(nome="Fazenda 2")
        s.add(f1); s.add(f2); s.commit(); s.refresh(f1); s.refresh(f2)
        joao = s.exec(select(Usuario).where(Usuario.username == "joao")).first()
        s.add(UsuarioFazenda(usuario_id=joao.id, fazenda_id=f1.id))
        s.add(UsuarioFazenda(usuario_id=joao.id, fazenda_id=f2.id))
        s.commit()
        f1_id = f1.id

    r = c.post("/auth/login", json={"username": "joao", "senha": "123", "manter_conectado": True})
    assert r.status_code == 200
    dados = r.json()
    assert dados["selecao_fazenda_necessaria"] is True
    token_inicial = dados["token"]

    r2 = c.post(
        "/auth/selecionar-fazenda", json={"fazenda_id": f1_id},
        headers={"Authorization": f"Bearer {token_inicial}"},
    )
    assert r2.status_code == 200
    payload = _validar_token_payload(r2.json()["token"])
    assert payload["lembrar"] is True
    assert TOKEN_VALIDADE_LONGA_S - 5 <= payload["exp"] - time.time() <= TOKEN_VALIDADE_LONGA_S + 5


def test_selecionar_fazenda_sem_manter_conectado_usa_validade_padrao(client):
    c, engine = client
    from sqlmodel import select
    with Session(engine) as s:
        f1 = Fazenda(nome="Fazenda 1")
        f2 = Fazenda(nome="Fazenda 2")
        s.add(f1); s.add(f2); s.commit(); s.refresh(f1); s.refresh(f2)
        joao = s.exec(select(Usuario).where(Usuario.username == "joao")).first()
        s.add(UsuarioFazenda(usuario_id=joao.id, fazenda_id=f1.id))
        s.add(UsuarioFazenda(usuario_id=joao.id, fazenda_id=f2.id))
        s.commit()
        f1_id = f1.id

    r = c.post("/auth/login", json={"username": "joao", "senha": "123"})
    assert r.status_code == 200
    token_inicial = r.json()["token"]

    r2 = c.post(
        "/auth/selecionar-fazenda", json={"fazenda_id": f1_id},
        headers={"Authorization": f"Bearer {token_inicial}"},
    )
    assert r2.status_code == 200
    payload = _validar_token_payload(r2.json()["token"])
    assert "lembrar" not in payload
    assert TOKEN_VALIDADE_S - 5 <= payload["exp"] - time.time() <= TOKEN_VALIDADE_S + 5
