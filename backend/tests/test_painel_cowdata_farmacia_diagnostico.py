"""
Diagnóstico da Farmácia (GET/POST /painel-cowdata/farmacia/diagnostico) —
audita, fazenda por fazenda, se o catálogo central chegou direito no
estoque do tenant. Ver docstring da seção em painel_cowdata_farmacia.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Estoque, Fazenda, MedicamentoComercial, PrincipioAtivo, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fa = Fazenda(nome="Jairo Nasser", ativa=True)
        fb = Fazenda(nome="Fazenda B", ativa=True)
        cowdata = Fazenda(nome="CowData", ativa=True, eh_empresa_cowdata=True)
        s.add_all([fa, fb, cowdata])
        s.commit()
        s.refresh(fa)
        s.refresh(fb)
        fa_id, fb_id = fa.id, fb.id
        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        s.add(dono)
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, fa_id, fb_id
    main.app.dependency_overrides.clear()


def _login(c):
    r = c.post("/auth/login", json={"username": "dono", "senha": "123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_medicamento_recem_criado_aparece_casado_nas_2_fazendas(client):
    c, engine, fa_id, fb_id = client
    h = _login(c)
    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Fenbendazol"}, headers=h).json()["id"]
    c.post("/painel-cowdata/farmacia/medicamentos", json={"nome_comercial": "Panacur Bovino", "principio_ativo_ids": [pa_id]}, headers=h)

    r = c.get("/painel-cowdata/farmacia/diagnostico", params={"fazenda_id": fa_id}, headers=h)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["casados"]) == 1
    assert corpo["casados"][0]["nome_comercial_central"] == "Panacur Bovino"
    assert corpo["orfaos"] == []
    assert corpo["ausentes"] == []


def test_item_orfao_aparece_e_pode_ser_vinculado(client):
    """Caso real reportado: "Draxxin KP" cadastrado direto na fazenda ANTES
    do medicamento existir no Painel CowData — o fan-out (que casa por nome
    exato) preserva o item antigo sem tocar nele, deixando-o sem vínculo."""
    c, engine, fa_id, fb_id = client
    h = _login(c)
    with Session(engine) as s:
        item = Estoque(nome="Draxxin KP", fazenda_id=fa_id, finalidade="Medicamento")
        s.add(item)
        s.commit()
        s.refresh(item)
        item_id = item.id

    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Tulatromicina"}, headers=h).json()["id"]
    med_id = c.post(
        "/painel-cowdata/farmacia/medicamentos",
        json={"nome_comercial": "Draxxin KP", "principio_ativo_ids": [pa_id], "laboratorio": "Zoetis"},
        headers=h,
    ).json()["id"]
    # O fan-out rodou na criação acima, mas viu o "Draxxin KP" já existente
    # na fazenda A e não mexeu nele (nunca sobrescreve dado do tenant).

    r = c.get("/painel-cowdata/farmacia/diagnostico", params={"fazenda_id": fa_id}, headers=h)
    corpo = r.json()
    assert [o["estoque_id"] for o in corpo["orfaos"]] == [item_id]
    assert corpo["casados"] == []  # nada casado NESTA fazenda ainda

    r_vinc = c.post(
        "/painel-cowdata/farmacia/diagnostico/vincular",
        json={"fazenda_id": fa_id, "estoque_id": item_id, "medicamento_comercial_id": med_id},
        headers=h,
    )
    assert r_vinc.status_code == 200, r_vinc.text
    corpo_item = r_vinc.json()
    assert corpo_item["nome"] == "Draxxin KP"  # nome do item mantido, não forçado
    assert corpo_item["medicamento_comercial_id"] == med_id
    assert corpo_item["principio_ativo"] == "Tulatromicina"
    assert corpo_item["laboratorio"] == "Zoetis"

    r2 = c.get("/painel-cowdata/farmacia/diagnostico", params={"fazenda_id": fa_id}, headers=h)
    corpo2 = r2.json()
    assert corpo2["orfaos"] == []
    assert len(corpo2["casados"]) == 1


def test_vincular_com_nome_diferente_preserva_nome_do_item(client):
    c, engine, fa_id, fb_id = client
    h = _login(c)
    with Session(engine) as s:
        item = Estoque(nome="Tulatromicina 100mg (genérico)", fazenda_id=fa_id, finalidade="Medicamento")
        s.add(item)
        s.commit()
        s.refresh(item)
        item_id = item.id

    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Tulatromicina"}, headers=h).json()["id"]
    med_id = c.post(
        "/painel-cowdata/farmacia/medicamentos",
        json={"nome_comercial": "Tulatromicina Injetável", "principio_ativo_ids": [pa_id]}, headers=h,
    ).json()["id"]

    r = c.post(
        "/painel-cowdata/farmacia/diagnostico/vincular",
        json={"fazenda_id": fa_id, "estoque_id": item_id, "medicamento_comercial_id": med_id},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["nome"] == "Tulatromicina 100mg (genérico)"


def test_vincular_item_ja_vinculado_e_bloqueado(client):
    c, engine, fa_id, fb_id = client
    h = _login(c)
    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Ivermectina"}, headers=h).json()["id"]
    med_id = c.post(
        "/painel-cowdata/farmacia/medicamentos", json={"nome_comercial": "Ivomec", "principio_ativo_ids": [pa_id]}, headers=h,
    ).json()["id"]
    with Session(engine) as s:
        item = s.exec(select(Estoque).where(Estoque.fazenda_id == fa_id, Estoque.nome == "Ivomec")).first()
        item_id = item.id

    r = c.post(
        "/painel-cowdata/farmacia/diagnostico/vincular",
        json={"fazenda_id": fa_id, "estoque_id": item_id, "medicamento_comercial_id": med_id},
        headers=h,
    )
    assert r.status_code == 400


def test_medicamento_ausente_em_fazenda_reativada_pode_ser_ativado(client):
    """Caso real: fazenda B foi 'reativada'/criada depois do medicamento já
    existir no central — o fan-out original não a alcançou."""
    c, engine, fa_id, fb_id = client
    h = _login(c)
    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Flunixin"}, headers=h).json()["id"]
    med_id = c.post(
        "/painel-cowdata/farmacia/medicamentos", json={"nome_comercial": "Banamine", "principio_ativo_ids": [pa_id]}, headers=h,
    ).json()["id"]
    with Session(engine) as s:
        # Simula "nunca alcançou": remove o item que o fan-out criou na fazenda B.
        item_b = s.exec(select(Estoque).where(Estoque.fazenda_id == fb_id, Estoque.nome == "Banamine")).first()
        s.delete(item_b)
        s.commit()

    r = c.get("/painel-cowdata/farmacia/diagnostico", params={"fazenda_id": fb_id}, headers=h)
    corpo = r.json()
    assert len(corpo["ausentes"]) == 1
    assert corpo["ausentes"][0]["nome_comercial"] == "Banamine"

    r_ativar = c.post(
        "/painel-cowdata/farmacia/diagnostico/ativar",
        json={"fazenda_id": fb_id, "medicamento_comercial_id": med_id}, headers=h,
    )
    assert r_ativar.status_code == 201, r_ativar.text
    corpo_item = r_ativar.json()
    assert corpo_item["nome"] == "Banamine"
    assert corpo_item["ativo"] is False and corpo_item["estocavel"] is False

    r2 = c.get("/painel-cowdata/farmacia/diagnostico", params={"fazenda_id": fb_id}, headers=h)
    assert r2.json()["ausentes"] == []


def test_ativar_quando_ja_existe_item_com_mesmo_nome_orienta_a_vincular(client):
    c, engine, fa_id, fb_id = client
    h = _login(c)
    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Cetoprofeno"}, headers=h).json()["id"]
    med_id = c.post(
        "/painel-cowdata/farmacia/medicamentos", json={"nome_comercial": "Ketofen", "principio_ativo_ids": [pa_id]}, headers=h,
    ).json()["id"]
    with Session(engine) as s:
        # Fan-out já criou o item real; simula que ele virou órfão (perdeu o vínculo).
        item = s.exec(select(Estoque).where(Estoque.fazenda_id == fa_id, Estoque.nome == "Ketofen")).first()
        item.medicamento_comercial_id = None
        s.add(item)
        s.commit()

    r = c.post(
        "/painel-cowdata/farmacia/diagnostico/ativar",
        json={"fazenda_id": fa_id, "medicamento_comercial_id": med_id}, headers=h,
    )
    assert r.status_code == 409
    assert "Vincular ao catálogo central" in r.json()["detail"]


def test_diagnostico_exige_fazenda_cliente_ativa(client):
    c, engine, fa_id, fb_id = client
    h = _login(c)
    r = c.get("/painel-cowdata/farmacia/diagnostico", params={"fazenda_id": 999999}, headers=h)
    assert r.status_code == 404


def test_listar_fazendas_farmacia(client):
    c, engine, fa_id, fb_id = client
    h = _login(c)
    r = c.get("/painel-cowdata/farmacia/fazendas", headers=h)
    assert r.status_code == 200
    nomes = {f["nome"] for f in r.json()}
    assert nomes == {"Jairo Nasser", "Fazenda B"}  # nunca a fazenda CowData
