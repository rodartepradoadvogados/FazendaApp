"""
Painel CowData > Parâmetros — visão agregada e edição em massa dos
parâmetros de ParametroFazenda em todas as fazendas-cliente ou nas
selecionadas. Ver fazenda/api/routers/painel_cowdata_parametros.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Fazenda, ParametroFazenda, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fa = Fazenda(nome="Fazenda A", ativa=True)
        fb = Fazenda(nome="Fazenda B", ativa=True)
        inativa = Fazenda(nome="Fazenda Inativa", ativa=False)
        s.add_all([fa, fb, inativa])
        s.commit()
        s.refresh(fa)
        s.refresh(fb)
        s.refresh(inativa)
        fa_id, fb_id, inativa_id = fa.id, fb.id, inativa.id

        s.add(ParametroFazenda(chave="pev_dias", fazenda_id=None, grupo="manejo", label="PEV", valor="45", tipo="int", unidade="dias"))
        # Fazenda B já personalizou esse parâmetro antes.
        s.add(ParametroFazenda(chave="pev_dias", fazenda_id=fb_id, grupo="manejo", label="PEV", valor="60", tipo="int", unidade="dias"))

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
        yield c, engine, fa_id, fb_id, inativa_id
    main.app.dependency_overrides.clear()


def _login(c, username="dono"):
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def _item(body, chave):
    for grupo in body["grupos"].values():
        for item in grupo["itens"]:
            if item["chave"] == chave:
                return item
    return None


def test_nao_dono_sem_area_e_bloqueado(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c, "admin-comum")
    r = c.get("/painel-cowdata/parametros/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_listar_fazendas_exclui_inativas(client):
    c, engine, fa_id, fb_id, inativa_id = client
    token = _login(c)
    r = c.get("/painel-cowdata/parametros/fazendas", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    ids = {f["id"] for f in r.json()}
    assert ids == {fa_id, fb_id}


def test_listar_mostra_valor_global_e_quem_personalizou(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    r = c.get("/painel-cowdata/parametros/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    item = _item(r.json(), "pev_dias")
    assert item["valor_global"] == 45
    assert item["personalizado_em"] == [fb_id]


def test_aplicar_em_todas_sobrescreve_global_e_toda_fazenda_ativa(client):
    """Mesma semântica de Cadastros globais: "Todas as fazendas ativas" é
    literal — sobrescreve inclusive quem já tinha personalizado (e também
    atualiza o padrão global, para fazenda nova já nascer com o novo
    valor). Só a seleção de fazendas específicas preserva o resto."""
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    headers = {"Authorization": f"Bearer {token}"}
    r = c.put("/painel-cowdata/parametros/pev_dias", json={"valor": 50}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["global_atualizado"] is True
    assert r.json()["atualizados"] == 2

    with Session(engine) as s:
        linhas = {l.fazenda_id: l.valor for l in s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "pev_dias")).all()}
        assert linhas[None] == "50"
        assert linhas[fa_id] == "50"
        assert linhas[fb_id] == "50"


def test_aplicar_em_fazendas_especificas_nao_toca_o_global(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    headers = {"Authorization": f"Bearer {token}"}
    r = c.put("/painel-cowdata/parametros/pev_dias", json={"valor": 99, "fazenda_ids": [fa_id]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["global_atualizado"] is False
    assert r.json()["atualizados"] == 1

    with Session(engine) as s:
        linhas = {l.fazenda_id: l.valor for l in s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "pev_dias")).all()}
        assert linhas[None] == "45", "global não devia mudar quando a seleção é específica"
        assert linhas[fa_id] == "99"
        assert linhas[fb_id] == "60"


def test_aplicar_em_fazenda_ja_personalizada_sobrescreve_a_selecionada(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    headers = {"Authorization": f"Bearer {token}"}
    r = c.put("/painel-cowdata/parametros/pev_dias", json={"valor": 33, "fazenda_ids": [fb_id]}, headers=headers)
    assert r.status_code == 200, r.text

    with Session(engine) as s:
        linhas = {l.fazenda_id: l.valor for l in s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "pev_dias")).all()}
        assert linhas[fb_id] == "33"


def test_chave_inexistente_404(client):
    c, engine, fa_id, fb_id, _ = client
    token = _login(c)
    r = c.put("/painel-cowdata/parametros/nao_existe", json={"valor": 1}, headers={"Authorization": f"Bearer {_login(c)}"})
    assert r.status_code == 404
