"""
GET/PUT /parametros/ precisam respeitar fazenda_id — antes disso, GET
devolvia TODAS as linhas de TODAS as fazendas juntas (sem filtro) e PUT
editava a primeira linha que batesse com a chave (também sem filtro): como
nada nunca criava uma linha fazenda-específica, toda fazenda-cliente lia e
editava o MESMO parâmetro global, silenciosamente. Ver
fazenda/api/routers/parametros.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, get_fazenda_atual_id, hash_senha
from fazenda.models import ContratoFazenda, Fazenda, ParametroFazenda, Usuario


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Usuario(username="admin", nome="Admin", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.add(ParametroFazenda(chave="pev_dias", fazenda_id=None, grupo="manejo", label="PEV", valor="45", tipo="int", unidade="dias"))
        # /parametros exige contrato ativo (ver main.py::_contrato_ativo).
        for fid in (1, 2, 3):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}", ativa=True))
            s.add(ContratoFazenda(fazenda_id=fid, plano="diamond", status="ativo"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _login(c):
    r = c.post("/auth/login", json={"username": "admin", "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def _com_fazenda(fid):
    import main
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fid


def _item(body, chave):
    for grupo in body["grupos"].values():
        for item in grupo["itens"]:
            if item["chave"] == chave:
                return item
    return None


def test_editar_numa_fazenda_nao_muda_o_valor_visto_por_outra(client):
    c, engine = client
    token = _login(c)
    headers = {"Authorization": f"Bearer {token}"}

    _com_fazenda(1)
    r = c.put("/parametros/pev_dias", json={"valor": 70}, headers=headers)
    assert r.status_code == 200, r.text

    _com_fazenda(2)
    r = c.get("/parametros/", headers=headers)
    assert _item(r.json(), "pev_dias")["valor"] == 45, "fazenda 2 não personalizou — devia continuar no padrão global"

    _com_fazenda(1)
    r = c.get("/parametros/", headers=headers)
    assert _item(r.json(), "pev_dias")["valor"] == 70


def test_get_sem_fazenda_no_token_mostra_so_o_padrao_global(client):
    c, engine = client
    token = _login(c)
    headers = {"Authorization": f"Bearer {token}"}

    _com_fazenda(1)
    c.put("/parametros/pev_dias", json={"valor": 70}, headers=headers)

    _com_fazenda(None)
    r = c.get("/parametros/", headers=headers)
    assert _item(r.json(), "pev_dias")["valor"] == 45


def test_get_nao_duplica_item_quando_fazenda_personalizou(client):
    c, engine = client
    token = _login(c)
    headers = {"Authorization": f"Bearer {token}"}

    _com_fazenda(1)
    c.put("/parametros/pev_dias", json={"valor": 70}, headers=headers)

    r = c.get("/parametros/", headers=headers)
    itens = [i for grupo in r.json()["grupos"].values() for i in grupo["itens"] if i["chave"] == "pev_dias"]
    assert len(itens) == 1


def test_editar_clona_a_linha_global_em_vez_de_mutar_ela(client):
    c, engine = client
    token = _login(c)
    headers = {"Authorization": f"Bearer {token}"}

    _com_fazenda(3)
    c.put("/parametros/pev_dias", json={"valor": 99}, headers=headers)

    with Session(engine) as s:
        linhas = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "pev_dias")).all()
        por_fazenda = {l.fazenda_id: l.valor for l in linhas}
        assert por_fazenda[None] == "45", "padrão global não podia ter sido alterado"
        assert por_fazenda[3] == "99"
