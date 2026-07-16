"""
Cálculo automático de grau de sangue da cria no parto (fazenda.rules.genetica)
e CRUD de Raça/Grau de sangue (Configurações > Cadastro).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, EstoqueSemen, GrauSangue, Raca, Servico, Touro


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
        c.engine = engine
        yield c

    main.app.dependency_overrides.clear()


def _seed_graus(engine):
    with Session(engine) as session:
        for nome, fracao in [
            ("PO Gir", 0.0), ("1/2 Holandês x Gir", 0.5), ("3/4 Holandês", 0.75),
            ("7/8 Holandês", 0.875), ("PO Holandês", 1.0),
        ]:
            session.add(GrauSangue(nome=nome, fracao_holandes=fracao))
        session.commit()


def test_parto_calcula_grau_sangue_mae_gir_pai_holandes(client):
    _seed_graus(client.engine)
    with Session(client.engine) as session:
        session.add(Animal(numero="100", sexo="F", raca="Gir", grau_sangue="PO Gir", ativo=True))
        session.add(Servico(numero_matriz="100", data_servico=date(2025, 1, 1), reprodutor="Touro Holandês X"))
        session.add(Touro(naab="7HO00001", nome="Touro Holandês X", raca="Holandês"))
        session.commit()

    resp = client.post("/reproducao/parto", json={
        "numero_matriz": "100",
        "data_parto": "2025-10-08",  # ~280 dias após o serviço
        "crias": [{"numero": "100-C1", "sexo": "F", "nasceu_viva": True}],
    })
    assert resp.status_code == 200, resp.text

    with Session(client.engine) as session:
        cria = session.exec(select(Animal).where(Animal.numero == "100-C1")).first()
        assert cria is not None
        assert cria.raca == "Girolando"
        assert cria.grau_sangue == "1/2 Holandês x Gir"


def test_parto_sem_pai_identificavel_mantem_raca_da_mae(client):
    _seed_graus(client.engine)
    with Session(client.engine) as session:
        session.add(Animal(numero="200", sexo="F", raca="Girolando", grau_sangue="3/4 Holandês", ativo=True))
        session.commit()

    resp = client.post("/reproducao/parto", json={
        "numero_matriz": "200",
        "data_parto": "2025-10-08",
        "crias": [{"numero": "200-C1", "sexo": "F", "nasceu_viva": True}],
    })
    assert resp.status_code == 200, resp.text

    with Session(client.engine) as session:
        cria = session.exec(select(Animal).where(Animal.numero == "200-C1")).first()
        assert cria is not None
        assert cria.raca == "Girolando"
        assert cria.grau_sangue is None


def test_crud_racas(client):
    resp = client.post("/cadastro/racas", json={"nome": "Nelore", "ativo": True})
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]

    resp = client.get("/cadastro/racas")
    assert resp.status_code == 200
    assert any(r["nome"] == "Nelore" for r in resp.json())

    resp = client.put(f"/cadastro/racas/{item_id}", json={"nome": "Nelore", "ativo": False})
    assert resp.status_code == 200
    assert resp.json()["ativo"] is False

    # Nome duplicado é rejeitado.
    client.post("/cadastro/racas", json={"nome": "Angus", "ativo": True})
    resp = client.post("/cadastro/racas", json={"nome": "Angus", "ativo": True})
    assert resp.status_code == 409


def test_crud_graus_sangue(client):
    resp = client.post("/cadastro/graus-sangue", json={"nome": "5/8 Holandês", "fracao_holandes": 0.625})
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["id"]
    assert resp.json()["fracao_holandes"] == 0.625

    resp = client.get("/cadastro/graus-sangue")
    assert resp.status_code == 200
    assert any(g["nome"] == "5/8 Holandês" for g in resp.json())

    resp = client.put(f"/cadastro/graus-sangue/{item_id}", json={"nome": "5/8 Holandês", "fracao_holandes": 0.6, "ativo": False})
    assert resp.status_code == 200
    assert resp.json()["fracao_holandes"] == 0.6
    assert resp.json()["ativo"] is False
