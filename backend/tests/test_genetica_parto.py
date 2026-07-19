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
from fazenda.models import Animal, EstoqueSemen, GrauSangue, Parto, Raca, Servico, Touro
from fazenda.api.routers.reproducao import backfill_categoria_crias, backfill_numero_cria_partos


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


def test_parto_insere_cria_automaticamente_na_categoria_bezerra_mamando(client):
    _seed_graus(client.engine)
    with Session(client.engine) as session:
        session.add(Animal(numero="486", sexo="F", raca="Girolando", grau_sangue="3/4 Holandês", ativo=True))
        session.commit()

    resp = client.post("/reproducao/parto", json={
        "numero_matriz": "486",
        "data_parto": "2025-10-08",
        "crias": [
            {"numero": "486-C1", "sexo": "F", "nasceu_viva": True},
            {"numero": "486-C2", "sexo": "M", "nasceu_viva": True},
        ],
    })
    assert resp.status_code == 200, resp.text

    with Session(client.engine) as session:
        femea = session.exec(select(Animal).where(Animal.numero == "486-C1")).first()
        macho = session.exec(select(Animal).where(Animal.numero == "486-C2")).first()
        assert femea.categoria_completa == "Bezerra Mamando"
        assert femea.categoria_abrev == "Bezerra"
        assert macho.categoria_completa == "Bezerro Mamando"
        assert macho.categoria_abrev == "Bezerro"


def test_backfill_categoria_crias_corrige_animais_ja_cadastrados_sem_categoria(client):
    with Session(client.engine) as session:
        # Cria já existente sem categoria (comportamento antigo do /parto) —
        # mae_numero preenchido indica que veio de um parto.
        session.add(Animal(numero="487", sexo="F", mae_numero="200", mae_nome="Vaca 200", ativo=True))
        # Animal sem mãe (ex.: comprado) — não deve ser tocado pelo backfill.
        session.add(Animal(numero="300", sexo="F", ativo=True))
        session.commit()

    with Session(client.engine) as session:
        backfill_categoria_crias(session)

    with Session(client.engine) as session:
        cria = session.exec(select(Animal).where(Animal.numero == "487")).first()
        comprado = session.exec(select(Animal).where(Animal.numero == "300")).first()
        assert cria.categoria_completa == "Bezerra Mamando"
        assert cria.categoria_abrev == "Bezerra"
        assert comprado.categoria_completa is None


def test_backfill_numero_cria_partos_associa_por_mae_e_data(client):
    from datetime import date

    with Session(client.engine) as session:
        # Parto importado do CSV reprodutivo (sem numero_cria) — a cria já
        # está cadastrada com mae_numero e nasceu na mesma data do parto.
        session.add(Parto(numero_matriz="500", data_parto=date(2026, 1, 10), ordem_parto=1))
        session.add(Animal(numero="500-C1", sexo="F", mae_numero="500", data_nasc=date(2026, 1, 10), ativo=True))
        # Parto gemelar — duas crias nascidas no mesmo dia.
        session.add(Parto(numero_matriz="600", data_parto=date(2026, 2, 1), ordem_parto=2, gemelar=True))
        session.add(Animal(numero="600-C1", sexo="F", mae_numero="600", data_nasc=date(2026, 2, 1), ativo=True))
        session.add(Animal(numero="600-C2", sexo="M", mae_numero="600", data_nasc=date(2026, 2, 1), ativo=True))
        # Parto sem cria cadastrada (natimorto) — não deve quebrar nem associar nada.
        session.add(Parto(numero_matriz="700", data_parto=date(2026, 3, 1), ordem_parto=1))
        session.commit()

    with Session(client.engine) as session:
        backfill_numero_cria_partos(session)

    with Session(client.engine) as session:
        p500 = session.exec(select(Parto).where(Parto.numero_matriz == "500")).first()
        p600 = session.exec(select(Parto).where(Parto.numero_matriz == "600")).first()
        p700 = session.exec(select(Parto).where(Parto.numero_matriz == "700")).first()
        assert p500.numero_cria_1 == "500-C1"
        assert {p600.numero_cria_1, p600.numero_cria_2} == {"600-C1", "600-C2"}
        assert p600.gemelar_sexo == "FM"
        assert p700.numero_cria_1 is None


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
