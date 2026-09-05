"""
Endpoint POST /painel-cowdata/fazendas/{destino_id}/sincronizar — ver
fazenda/api/routers/painel_cowdata_sincronizacao.py. A lógica de cópia em si
já é coberta a fundo por tests/test_replicacao_fazenda.py; aqui só o
contrato HTTP (autorização, formato da resposta, tradução das recusas em
409/500).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Animal, Fazenda, Parto, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        origem = Fazenda(nome="Jairo Nasser", ativa=True, eh_teste=False)
        destino_teste = Fazenda(nome="Fazenda Teste", ativa=True, eh_teste=True)
        destino_invalido = Fazenda(nome="Outra fazenda real", ativa=True, eh_teste=False)
        s.add_all([origem, destino_teste, destino_invalido])
        s.commit()
        s.refresh(origem)
        s.refresh(destino_teste)
        s.refresh(destino_invalido)
        origem_id, destino_id, destino_invalido_id = origem.id, destino_teste.id, destino_invalido.id

        s.add(Animal(numero="1", fazenda_id=origem_id, sexo="F"))
        s.add(Parto(numero_matriz="1", fazenda_id=origem_id, data_parto=date(2026, 1, 1)))

        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        comum = Usuario(username="comum", nome="Comum", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com")
        s.add_all([dono, comum])
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, origem_id, destino_id, destino_invalido_id
    main.app.dependency_overrides.clear()


def _login(c, username):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_sem_area_painel_e_bloqueado(client):
    c, origem_id, destino_id, _ = client
    token = _login(c, "comum")
    r = c.post(
        f"/painel-cowdata/fazendas/{destino_id}/sincronizar",
        json={"origem_id": origem_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_dono_sincroniza_com_sucesso(client):
    c, origem_id, destino_id, _ = client
    token = _login(c, "dono")
    r = c.post(
        f"/painel-cowdata/fazendas/{destino_id}/sincronizar",
        json={"origem_id": origem_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "ok"
    assert corpo["origem"] == "Jairo Nasser"
    assert corpo["destino"] == "Fazenda Teste"
    assert corpo["linhas_copiadas"] >= 2
    assert isinstance(corpo["avisos"], list)
    assert isinstance(corpo["duracao_s"], float)


def test_destino_sem_eh_teste_recusa_409(client):
    c, origem_id, _, destino_invalido_id = client
    token = _login(c, "dono")
    r = c.post(
        f"/painel-cowdata/fazendas/{destino_invalido_id}/sincronizar",
        json={"origem_id": origem_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409


def test_origem_igual_destino_recusa_409(client):
    c, origem_id, destino_id, _ = client
    token = _login(c, "dono")
    r = c.post(
        f"/painel-cowdata/fazendas/{destino_id}/sincronizar",
        json={"origem_id": destino_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409
