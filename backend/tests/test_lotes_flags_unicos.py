"""
Testes da validação de unicidade das flags pre_parto / status_lactacao="seca"
em POST/PUT /lotes/ — evita que um cadastro deixe dois lotes disputando a
mesma identidade (ex.: dois lotes marcados como "Secas"), o que faria toda
regra que busca "o" lote por essa flag (secagem, calendário sanitário) achar
o lote errado silenciosamente.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c

    main.app.dependency_overrides.clear()


def test_lote_nao_pode_ser_pre_parto_e_seca_ao_mesmo_tempo(client):
    r = client.post("/lotes/", json={"codigo": "04", "nome": "Pré-parto", "pre_parto": True, "status_lactacao": "seca"})
    assert r.status_code == 400


def test_criar_segundo_lote_pre_parto_e_rejeitado(client):
    r1 = client.post("/lotes/", json={"codigo": "04", "nome": "Pré-parto", "pre_parto": True})
    assert r1.status_code == 200
    r2 = client.post("/lotes/", json={"codigo": "06", "nome": "Outro pré-parto", "pre_parto": True})
    assert r2.status_code == 400
    assert "Pré-parto" in r2.json()["detail"]


def test_criar_segundo_lote_seca_e_rejeitado(client):
    r1 = client.post("/lotes/", json={"codigo": "05", "nome": "Secas", "status_lactacao": "seca"})
    assert r1.status_code == 200
    r2 = client.post("/lotes/", json={"codigo": "07", "nome": "Outro secas", "status_lactacao": "seca"})
    assert r2.status_code == 400
    assert "Seca" in r2.json()["detail"]


def test_atualizar_lote_para_flag_ja_usada_por_outro_e_rejeitado(client):
    client.post("/lotes/", json={"codigo": "04", "nome": "Pré-parto", "pre_parto": True})
    r2 = client.post("/lotes/", json={"codigo": "05", "nome": "Secas"})
    lote_id = r2.json()["id"]
    r = client.put(f"/lotes/{lote_id}", json={"codigo": "05", "nome": "Secas", "pre_parto": True})
    assert r.status_code == 400


def test_atualizar_o_proprio_lote_mantendo_sua_flag_e_permitido(client):
    r1 = client.post("/lotes/", json={"codigo": "05", "nome": "Secas", "status_lactacao": "seca"})
    lote_id = r1.json()["id"]
    r = client.put(f"/lotes/{lote_id}", json={"codigo": "05", "nome": "Vacas Secas", "status_lactacao": "seca"})
    assert r.status_code == 200
    assert r.json()["nome"] == "Vacas Secas"


def test_dois_lotes_com_flags_diferentes_sao_permitidos(client):
    r1 = client.post("/lotes/", json={"codigo": "04", "nome": "Pré-parto", "pre_parto": True})
    r2 = client.post("/lotes/", json={"codigo": "05", "nome": "Secas", "status_lactacao": "seca"})
    assert r1.status_code == 200
    assert r2.status_code == 200
