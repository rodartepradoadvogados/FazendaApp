"""
Painel CowData > Farmácia — catálogo global (categoria/doença, princípio
ativo, medicamento) + fan-out do medicamento pra Estoque de toda
fazenda-cliente. Ver fazenda/api/routers/painel_cowdata_farmacia.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import (
    Estoque, EstoqueCategoriaMedicamento, Fazenda, IndicacaoTerapeutica, MedicamentoComercial, PrincipioAtivo, Usuario,
)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fa = Fazenda(nome="Fazenda A", ativa=True)
        fb = Fazenda(nome="Fazenda B", ativa=True)
        cowdata = Fazenda(nome="CowData", ativa=True, eh_empresa_cowdata=True)
        s.add_all([fa, fb, cowdata])
        s.commit()
        s.refresh(fa)
        s.refresh(fb)
        fa_id, fb_id = fa.id, fb.id

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
        yield c, engine, fa_id, fb_id
    main.app.dependency_overrides.clear()


def _login(c, username="dono"):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def test_nao_dono_sem_area_e_bloqueado(client):
    c, engine, fa_id, fb_id = client
    token = _login(c, "admin-comum")
    r = c.get("/painel-cowdata/farmacia/principios", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_cria_categoria_global_valida_tipo(client):
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}
    r = c.post("/painel-cowdata/farmacia/categorias", json={"nome": "Mastite", "tipo": "doenca"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["fazenda_id"] is None

    ruim = c.post("/painel-cowdata/farmacia/categorias", json={"nome": "X", "tipo": "invalido"}, headers=h)
    assert ruim.status_code == 400


def test_cria_principio_global_e_medicamento_faz_fanout_inativo(client):
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    r_pa = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Meloxicam"}, headers=h)
    assert r_pa.status_code == 201, r_pa.text
    pa_id = r_pa.json()["id"]
    assert r_pa.json()["fazenda_id"] is None

    r_doenca = c.post("/painel-cowdata/farmacia/categorias", json={"nome": "Mastite", "tipo": "doenca"}, headers=h)
    doenca_id = r_doenca.json()["id"]

    r_med = c.post(
        "/painel-cowdata/farmacia/medicamentos",
        json={"nome_comercial": "Maxicam 2%", "principio_ativo_ids": [pa_id], "doenca_ids": [doenca_id], "laboratorio": "Ourofino"},
        headers=h,
    )
    assert r_med.status_code == 201, r_med.text
    corpo = r_med.json()
    assert corpo["principio_ativo_ids"] == [pa_id]
    assert corpo["doenca_ids"] == [doenca_id]
    assert corpo["fan_out"] == {"criados": 2, "ja_existiam": 0}

    with Session(engine) as s:
        itens = s.exec(select(Estoque).where(Estoque.nome == "Maxicam 2%")).all()
        assert len(itens) == 2
        for item in itens:
            assert item.fazenda_id in (fa_id, fb_id)
            assert item.ativo is False
            assert item.estocavel is False
            assert item.finalidade == "Medicamento"
            assert item.categoria == "Medicamentos"  # não confundir com classificacao_medicamento (a categoria médica)
            assert item.classificacao_medicamento is None  # nenhuma foi escolhida no cadastro deste teste
            assert item.principio_ativo_id == pa_id
            assert item.medicamento_comercial_id == corpo["id"]

        indicacoes = s.exec(select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.fazenda_id.is_(None))).all()
        assert len(indicacoes) == 1
        assert indicacoes[0].principio_ativo_id == pa_id and indicacoes[0].doenca_id == doenca_id


def test_fanout_nunca_sobrescreve_item_ja_existente_no_tenant(client):
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    with Session(engine) as s:
        s.add(Estoque(nome="Maxicam 2%", fazenda_id=fa_id, ativo=True, estocavel=True, quantidade=10))
        s.commit()

    r_pa = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Meloxicam"}, headers=h)
    pa_id = r_pa.json()["id"]
    r_med = c.post(
        "/painel-cowdata/farmacia/medicamentos",
        json={"nome_comercial": "Maxicam 2%", "principio_ativo_ids": [pa_id]},
        headers=h,
    )
    assert r_med.status_code == 201
    assert r_med.json()["fan_out"] == {"criados": 1, "ja_existiam": 1}

    with Session(engine) as s:
        item_fa = s.exec(select(Estoque).where(Estoque.nome == "Maxicam 2%", Estoque.fazenda_id == fa_id)).first()
        assert item_fa.ativo is True and item_fa.quantidade == 10  # dado real do tenant, intocado


def test_multi_principio_no_medicamento_global(client):
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}
    pa1 = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Diclofenaco"}, headers=h).json()["id"]
    pa2 = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Dexametasona"}, headers=h).json()["id"]

    r_med = c.post(
        "/painel-cowdata/farmacia/medicamentos",
        json={"nome_comercial": "Combo XYZ", "principio_ativo_ids": [pa1, pa2]},
        headers=h,
    )
    assert r_med.status_code == 201
    assert r_med.json()["principio_ativo_ids"] == [pa1, pa2]
    with Session(engine) as s:
        m = s.exec(select(MedicamentoComercial).where(MedicamentoComercial.nome_comercial == "Combo XYZ")).first()
        assert m.principio_ativo_id == pa1  # principal = primeiro da lista


def test_excluir_principio_bloqueia_se_medicamento_usa(client):
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}
    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Meloxicam"}, headers=h).json()["id"]
    c.post("/painel-cowdata/farmacia/medicamentos", json={"nome_comercial": "Maxicam 2%", "principio_ativo_ids": [pa_id]}, headers=h)

    r = c.delete(f"/painel-cowdata/farmacia/principios/{pa_id}", headers=h)
    assert r.status_code == 400


def test_fanout_propaga_categoria_medicamento_carencia_e_lactacao(client):
    """Pedido do usuário (01/09/2026): cadastrar Categoria (medicamento),
    carência leite/carne e "proibido em lactação" no medicamento global e ver
    tudo isso já preenchido no item de Estoque fanned-out — sem precisar
    redigitar em cada fazenda."""
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}
    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Tulatromicina"}, headers=h).json()["id"]
    cat_id = c.post("/painel-cowdata/farmacia/categorias-medicamento", json={"nome": "Antibiótico"}, headers=h).json()["id"]
    r_med = c.post(
        "/painel-cowdata/farmacia/medicamentos",
        json={
            "nome_comercial": "Draxxin KP", "principio_ativo_ids": [pa_id], "laboratorio": "Zoetis",
            "categoria_medicamento_ids": [cat_id], "proibido_lactacao": True, "carencia_carne_dias": 18,
        },
        headers=h,
    )
    assert r_med.status_code == 201, r_med.text
    assert r_med.json()["categoria_medicamento_ids"] == [cat_id]
    assert r_med.json()["classificacao_medicamento"] == "Antibiótico"  # espelho do escalar legado

    with Session(engine) as s:
        item = s.exec(select(Estoque).where(Estoque.nome == "Draxxin KP", Estoque.fazenda_id == fa_id)).first()
        assert item.categoria == "Medicamentos"
        assert item.classificacao_medicamento == "Antibiótico"
        assert item.laboratorio == "Zoetis"
        vinculo = s.exec(
            select(EstoqueCategoriaMedicamento).where(EstoqueCategoriaMedicamento.estoque_id == item.id)
        ).first()
        assert vinculo is not None and vinculo.categoria_medicamento_id == cat_id
        assert item.proibido_lactacao is True
        assert item.carencia_carne_dias == 18
        assert item.carencia_leite_dias is None  # não informado — nunca vira zero


def test_catalogos_laboratorio_categoria_classificacao_crud(client):
    """CRUD básico dos 3 catálogos novos (Fase B) — mesmo padrão de /principios."""
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}

    for prefixo, nome in [
        ("laboratorios", "Ourofino"), ("categorias-medicamento", "Antiparasitário"),
        ("classificacoes-medicamento", "Controlado"),
    ]:
        r_criar = c.post(f"/painel-cowdata/farmacia/{prefixo}", json={"nome": nome}, headers=h)
        assert r_criar.status_code == 201, r_criar.text
        item_id = r_criar.json()["id"]
        assert r_criar.json()["fazenda_id"] is None

        r_dup = c.post(f"/painel-cowdata/farmacia/{prefixo}", json={"nome": nome}, headers=h)
        assert r_dup.status_code == 409

        r_listar = c.get(f"/painel-cowdata/farmacia/{prefixo}", headers=h)
        assert nome in [i["nome"] for i in r_listar.json()]

        r_editar = c.put(f"/painel-cowdata/farmacia/{prefixo}/{item_id}", json={"nome": nome, "ativo": False}, headers=h)
        assert r_editar.status_code == 200
        assert r_editar.json()["ativo"] is False


def test_categoria_e_classificacao_medicamento_sao_cumulativas(client):
    """Pedido do usuário (01/09/2026): "categoria e classificação do
    medicamento pode ser cumulativo, podendo cadastrar mais de 1"."""
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}
    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Meloxicam"}, headers=h).json()["id"]
    cat1 = c.post("/painel-cowdata/farmacia/categorias-medicamento", json={"nome": "Anti-inflamatório"}, headers=h).json()["id"]
    cat2 = c.post("/painel-cowdata/farmacia/categorias-medicamento", json={"nome": "Analgésico"}, headers=h).json()["id"]
    cla1 = c.post("/painel-cowdata/farmacia/classificacoes-medicamento", json={"nome": "Genérico"}, headers=h).json()["id"]
    cla2 = c.post("/painel-cowdata/farmacia/classificacoes-medicamento", json={"nome": "Uso controlado"}, headers=h).json()["id"]

    r_med = c.post(
        "/painel-cowdata/farmacia/medicamentos",
        json={
            "nome_comercial": "Maxicam 2%", "principio_ativo_ids": [pa_id],
            "categoria_medicamento_ids": [cat1, cat2], "classificacao_medicamento_ids": [cla1, cla2],
        },
        headers=h,
    )
    assert r_med.status_code == 201, r_med.text
    corpo = r_med.json()
    assert corpo["categoria_medicamento_ids"] == [cat1, cat2]
    assert corpo["classificacao_medicamento_ids"] == [cla1, cla2]
    assert corpo["classificacao_medicamento"] == "Anti-inflamatório"  # 1ª categoria espelhada no escalar legado


def test_fanout_pula_fazenda_cowdata_interna(client):
    c, engine, fa_id, fb_id = client
    token = _login(c)
    h = {"Authorization": f"Bearer {token}"}
    pa_id = c.post("/painel-cowdata/farmacia/principios", json={"nome": "Meloxicam"}, headers=h).json()["id"]
    r_med = c.post("/painel-cowdata/farmacia/medicamentos", json={"nome_comercial": "Maxicam 2%", "principio_ativo_ids": [pa_id]}, headers=h)
    assert r_med.json()["fan_out"]["criados"] == 2  # só fa_id/fb_id, nunca a fazenda CowData interna
