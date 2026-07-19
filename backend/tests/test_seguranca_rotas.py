"""
Teste de proteção de rotas — mitiga o risco "autorização centralizada frágil"
(fácil esquecer de proteger um router novo em main.py, ver `_protegido` /
`exigir_modulo` em cada `app.include_router`).

Roda contra o schema OpenAPI real (o mesmo que alimenta /docs), então não
depende de como o FastAPI organiza as rotas internamente — só do que de fato
fica exposto pela API. Chama cada rota sem token e garante que nenhuma
responde com sucesso (2xx): se alguém registrar um router novo sem
`dependencies=` (ou sem proteção interna por rota), este teste quebra.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database

# Rotas intencionalmente públicas — cada uma documentada no próprio main.py
# (ou no router) no ponto em que é registrada sem exigir login.
ROTAS_PUBLICAS = {
    ("POST", "/auth/login"),
    ("GET", "/"),
    ("GET", "/health"),
    ("POST", "/telegram/webhook"),
    ("GET", "/telegram/status"),
    ("GET", "/news/"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
}


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c


def test_toda_rota_nao_publica_exige_autenticacao(client):
    schema = client.get("/openapi.json").json()
    falhas = []
    for path, metodos in schema["paths"].items():
        rota_teste = re.sub(r"\{[^}]+\}", "1", path)
        for metodo in metodos:
            verbo = metodo.upper()
            if (verbo, path) in ROTAS_PUBLICAS:
                continue
            corpo = {} if verbo in ("POST", "PUT", "PATCH") else None
            resp = client.request(verbo, rota_teste, json=corpo)
            if 200 <= resp.status_code < 300:
                falhas.append((verbo, path, resp.status_code))
    assert not falhas, f"Rotas respondendo com sucesso SEM autenticação (risco de vazamento): {falhas}"
