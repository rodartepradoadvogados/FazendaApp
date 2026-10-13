"""
Plano Financeiro §1.9 — checklist de primeiro acesso em função dos módulos
contratados: fazenda só-Financeiro não recebe lote/rebanho/app de campo;
fazenda com rebanho recebe o mesmo de sempre.
"""
from __future__ import annotations

import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.api.routers.onboarding import PASSOS_ONBOARDING
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, Usuario
from fazenda.models.planos import PLANOS_CATALOGO

FAZENDAS = {
    1: ["financeiro", "pedidos"],
    2: list(PLANOS_CATALOGO["standard"]["modulos"]),
    3: list(PLANOS_CATALOGO["gold"]["modulos"]),
    4: ["rebanho", "financeiro"],
}


class _FakeUser:
    id = 7
    papel = "operador"
    ativo = True
    username = "peao.teste"
    permissoes = "financeiro"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    with Session(engine) as s:
        s.add(Usuario(id=7, username=_FakeUser.username, senha_hash="x", papel="operador", ativo=True, permissoes="financeiro"))
        for fid in FAZENDAS:
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.commit()
        for fid, modulos in FAZENDAS.items():
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for m in modulos:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=m, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _como_fazenda(fid):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fid


def test_so_financeiro_recebe_os_cinco_passos_do_financeiro(client):
    _como_fazenda(1)
    corpo = client.get("/onboarding").json()
    assert [p["label"] for p in corpo["passos"]] == [
        "Cadastre suas contas bancárias", "Carregue o plano de contas", "Lance a primeira conta a pagar",
        "Convide seu contador", "Confira a Agenda",
    ]
    texto = " ".join(p["label"].lower() + p["rota"] for p in corpo["passos"])
    assert "lote" not in texto and "rebanho" not in texto and "/app" not in texto


@pytest.mark.parametrize("fid", [2, 3, 4])
def test_fazenda_com_rebanho_recebe_o_checklist_de_sempre(client, fid):
    _como_fazenda(fid)
    corpo = client.get("/onboarding").json()
    assert [(p["chave"], p["label"], p["rota"]) for p in corpo["passos"]] == [
        (p["chave"], p["label"], p["rota"]) for p in PASSOS_ONBOARDING
    ]


def test_sem_fazenda_no_recorte_segue_o_legado(client):
    """Direto na função (pela API, sem fazenda selecionada a requisição nem chega aqui: 409)."""
    from fazenda.api.routers.onboarding import passos_da_fazenda
    with Session(database.engine) as s:
        assert passos_da_fazenda(s, None) is PASSOS_ONBOARDING


def test_concluir_passos_do_financeiro_fecha_o_checklist(client):
    _como_fazenda(1)
    for chave in ("contas_bancarias", "plano_de_contas", "primeira_conta_a_pagar", "convidar_contador"):
        r = client.post(f"/onboarding/passos/{chave}/concluir")
        assert r.status_code == 200, r.text
    assert r.json()["tudo_concluido"] is False
    r = client.post("/onboarding/passos/conferir_agenda/concluir")
    assert r.json()["tudo_concluido"] is True
    assert all(p["concluido"] for p in r.json()["passos"])


def test_passo_invalido_continua_400(client):
    _como_fazenda(1)
    assert client.post("/onboarding/passos/inexistente/concluir").status_code == 400
