"""
Plano Financeiro, fase 1.3 — o preço do plano é fato do CONTRATO.

Ida-e-volta (regra do AGENTS.md): o dono edita o preço do plano 200 -> 230,
o catálogo mostra 230, mas o contrato JÁ aprovado continua em 200 em todos os
lugares que cobram (GET contrato, Asaas, boleto/Pix, MRR); o contrato aprovado
DEPOIS congela 230. Re-salvar o mesmo plano não recongela; trocar o plano de
um contrato ativo recongela pelo catálogo de hoje.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, Fazenda
from fazenda.models.planos import PLANOS_CATALOGO, PrecoPlano, preco_mensal_do_contrato

EMAIL_DONO = "jairodarte@gmail.com"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=2, nome="Fazenda Antiga"))
        s.add(Fazenda(id=3, nome="Fazenda Nova"))
        s.commit()
        s.add(ContratoFazenda(fazenda_id=2, status="aguardando_aprovacao"))
        s.add(ContratoFazenda(fazenda_id=3, status="aguardando_aprovacao"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _Fake:
        id = 1
        papel = "admin"
        ativo = True
        username = "dono"
        nome = "Jairo"
        email = EMAIL_DONO
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _Fake()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _nao_dono():
    import main
    from fazenda.auth import get_current_user

    class _Comum:
        id = 9
        papel = "admin"
        ativo = True
        username = "comum"
        email = "comum@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _Comum()


def _aprovar(c, fazenda_id: int, plano: str):
    r = c.put(f"/fazendas/{fazenda_id}/contrato", json={"plano": plano, "modulos": []})
    assert r.status_code == 200, r.text
    r = c.post(f"/fazendas/{fazenda_id}/contrato/aprovar")
    assert r.status_code == 200, r.text
    return r.json()


def _valores_cobrados(c, engine, fazenda_id: int) -> dict:
    """O mesmo contrato lido por todos os consumidores de preço."""
    from fazenda.api.routers import asaas, cobranca

    with Session(engine) as s:
        return {
            "get_contrato": c.get(f"/fazendas/{fazenda_id}/contrato").json()["preco_mensal"],
            "asaas": asaas._valor_mensal(s, fazenda_id),
            "cobranca": cobranca._valor_mensal(s, fazenda_id),
        }


def test_catalogo_traz_os_cinco_planos_com_formato_do_contrato(client):
    c, _ = client
    r = c.get("/fazendas/catalogo/planos")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert set(corpo) == {"standard", "silver", "gold", "diamond", "financeiro"}
    fin = corpo["financeiro"]
    assert fin == {
        "nome": "Financeiro", "modulos": ["financeiro", "pedidos"], "preco": 200.0, "preco_padrao": 200.0,
        "atualizado_em": None, "atualizado_por": None,
    }
    for chave, plano in corpo.items():
        assert set(plano) == {"nome", "preco", "preco_padrao", "modulos", "atualizado_em", "atualizado_por"}
        assert plano["preco"] == PLANOS_CATALOGO[chave]["preco"]


def test_ida_e_volta_200_para_230_nao_muda_contrato_ja_aprovado(client):
    c, engine = client
    _aprovar(c, 2, "financeiro")
    assert _valores_cobrados(c, engine, 2) == {"get_contrato": 200.0, "asaas": 200.0, "cobranca": 200.0}
    assert c.get("/fazendas/2/contrato").json()["preco_mensal_fechado"] == 200.0

    # Dono edita o preço do plano.
    r = c.put("/fazendas/catalogo/precos-plano/financeiro", json={"preco": 230})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["plano"] == "financeiro" and corpo["preco"] == 230.0 and corpo["preco_padrao"] == 200.0
    assert corpo["atualizado_por"] == "Jairo" or corpo["atualizado_por"] is None  # usuário fake não está no banco
    assert corpo["atualizado_em"]

    # Catálogo mostra 230 ...
    assert c.get("/fazendas/catalogo/planos").json()["financeiro"]["preco"] == 230.0
    # ... e o contrato já aprovado continua em 200 em TODO lugar que cobra.
    assert _valores_cobrados(c, engine, 2) == {"get_contrato": 200.0, "asaas": 200.0, "cobranca": 200.0}
    visto = c.get("/fazendas/2/contrato").json()
    assert visto["preco_mensal_fechado"] == 200.0
    assert visto["preco_catalogo_hoje"] == 230.0
    assert c.get("/fazendas/catalogo/resumo-cowdata").json()["mrr"] == 200.0

    # Contrato aprovado depois congela 230.
    _aprovar(c, 3, "financeiro")
    assert _valores_cobrados(c, engine, 3) == {"get_contrato": 230.0, "asaas": 230.0, "cobranca": 230.0}
    assert c.get("/fazendas/3/contrato").json()["preco_mensal_fechado"] == 230.0
    assert c.get("/fazendas/catalogo/resumo-cowdata").json()["mrr"] == 430.0


def test_rascunho_le_o_catalogo_ao_vivo_e_congela_so_na_aprovacao(client):
    c, engine = client
    r = c.put("/fazendas/2/contrato", json={"plano": "financeiro", "modulos": []})
    assert r.json()["preco_mensal"] == 200.0 and r.json()["preco_mensal_fechado"] is None
    c.put("/fazendas/catalogo/precos-plano/financeiro", json={"preco": 210})
    assert c.get("/fazendas/2/contrato").json()["preco_mensal"] == 210.0  # ainda rascunho
    r = c.post("/fazendas/2/contrato/aprovar")
    assert r.json()["preco_mensal_fechado"] == 210.0
    c.put("/fazendas/catalogo/precos-plano/financeiro", json={"preco": 250})
    assert c.get("/fazendas/2/contrato").json()["preco_mensal"] == 210.0


def test_resalvar_mesmo_plano_nao_recongela_mas_trocar_de_plano_recongela(client):
    c, engine = client
    _aprovar(c, 2, "financeiro")
    c.put("/fazendas/catalogo/precos-plano/financeiro", json={"preco": 230})

    # Mesmo plano: não recongela (nem a linha do pacote muda de preço).
    r = c.put("/fazendas/2/contrato", json={"plano": "financeiro", "modulos": []})
    assert r.json()["preco_mensal"] == 200.0 and r.json()["preco_mensal_fechado"] == 200.0
    assert {m["modulo"]: m["preco"] for m in r.json()["modulos"]}["financeiro"] == 200.0

    # Plano diferente em contrato ATIVO: recongela pelo catálogo de hoje.
    c.put("/fazendas/catalogo/precos-plano/standard", json={"preco": 260})
    r = c.put("/fazendas/2/contrato", json={"plano": "standard", "modulos": []})
    assert r.json()["preco_mensal"] == 260.0 and r.json()["preco_mensal_fechado"] == 260.0
    assert _valores_cobrados(c, engine, 2)["asaas"] == 260.0

    # Sob medida: sem preço de pacote congelado, soma dos módulos.
    r = c.put("/fazendas/2/contrato", json={"plano": None, "modulos": [{"modulo": "financeiro", "preco": 40.0}]})
    assert r.json()["preco_mensal"] == 40.0 and r.json()["preco_mensal_fechado"] is None
    assert r.json()["preco_catalogo_hoje"] is None


def test_reaprovar_contrato_suspenso_nao_recongela(client):
    c, engine = client
    _aprovar(c, 2, "financeiro")
    c.post("/fazendas/2/contrato/suspender")
    c.put("/fazendas/catalogo/precos-plano/financeiro", json={"preco": 999})
    r = c.post("/fazendas/2/contrato/aprovar")
    assert r.json()["preco_mensal"] == 200.0


def test_put_preco_plano_valida_entrada_e_so_dono(client):
    c, engine = client
    assert c.put("/fazendas/catalogo/precos-plano/inexistente", json={"preco": 10}).status_code == 400
    assert c.put("/fazendas/catalogo/precos-plano/financeiro", json={"preco": -1}).status_code == 400
    assert c.put("/fazendas/catalogo/precos-plano/financeiro", json={"preco": 0}).status_code == 200
    with Session(engine) as s:
        assert s.get(PrecoPlano, "financeiro").preco == 0.0
    _nao_dono()
    assert c.put("/fazendas/catalogo/precos-plano/financeiro", json={"preco": 10}).status_code == 403
    assert c.get("/fazendas/catalogo/planos").status_code == 403


def test_funcao_unica_cai_no_padrao_sem_linha_em_preco_plano(client):
    c, engine = client
    with Session(engine) as s:
        contrato = s.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == 2)).one()
        contrato.plano = "gold"
        assert preco_mensal_do_contrato(s, contrato) == 420.0
        contrato.preco_mensal_fechado = 399.0
        assert preco_mensal_do_contrato(s, contrato) == 399.0
