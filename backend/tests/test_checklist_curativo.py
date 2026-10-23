"""
Checklist do protocolo CURATIVO — GET /cadastro/checklist-template?tipo=curativo.

O template do curativo morava no módulo do checklist do preventivo antigo
(apagado em 2026). Só a parte do curativo ficou (rules/checklist_curativo.py):
o padrão em código vale até a fazenda ter linhas próprias; a linha da fazenda
vence a global; os tipos "vacina"/"exame" não existem mais.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ChecklistTemplateItem, ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules.checklist_curativo import TEMPLATE_PADRAO_CURATIVO


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _sessao():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "teste@example.com"
        permissoes = ""

    estado = {"fazenda": 1}
    main.app.dependency_overrides[database.get_session] = _sessao
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: estado["fazenda"]
    with TestClient(main.app) as c:
        c.estado = estado
        yield c, engine
    main.app.dependency_overrides.clear()


def test_sem_linhas_devolve_o_padrao_em_codigo(client):
    c, _ = client
    r = c.get("/cadastro/checklist-template", params={"tipo": "curativo"})
    assert r.status_code == 200, r.text
    assert [(i["chave"], i["nome"], i["ordem"]) for i in r.json()] == list(TEMPLATE_PADRAO_CURATIVO)


def test_tipo_padrao_e_curativo_e_preventivo_nao_existe_mais(client):
    c, _ = client
    assert c.get("/cadastro/checklist-template").status_code == 200
    for tipo in ("vacina", "exame"):
        assert c.get("/cadastro/checklist-template", params={"tipo": tipo}).status_code == 400


def test_linha_da_fazenda_vence_a_global_e_nao_vaza(client):
    c, engine = client
    with Session(engine) as s:
        s.add(ChecklistTemplateItem(tipo="curativo", chave="estoque", nome="Global", ordem=1))
        s.add(ChecklistTemplateItem(tipo="curativo", chave="estoque", nome="Da fazenda 1", ordem=1, fazenda_id=1))
        s.add(ChecklistTemplateItem(tipo="curativo", chave="custom", nome="Segredo F1", ordem=2, fazenda_id=1))
        s.commit()
    f1 = c.get("/cadastro/checklist-template").json()
    assert [i["nome"] for i in f1] == ["Da fazenda 1", "Segredo F1"]
    c.estado["fazenda"] = 2
    f2 = c.get("/cadastro/checklist-template").json()
    assert [i["nome"] for i in f2] == ["Global"]
