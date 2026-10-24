"""
Leomir (24/10/2026): funcionário com o módulo "rebanho" abria Movimentar animais no app, mas a lista de lotes não aparecia.
`GET /lotes/` exigia "parametros" (Configurações); a movimentação exige "rebanho". A LEITURA da lista passou a valer para
quem usa lote em alguma tela; cadastro/edição continuam só com "parametros".
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Lote


class _Usuario:
    papel = "operador"
    ativo = True

    def __init__(self, id_: int, permissoes: str):
        self.id = id_
        self.permissoes = permissoes
        self.username = f"u{id_}"


@pytest.fixture
def cliente():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with Session(engine) as s:
        s.add(Lote(codigo="04", nome="Pós-parto/Tratamento", ativo=True))
        s.commit()

    def como(permissoes: str):
        main.app.dependency_overrides[get_current_user] = lambda: _Usuario(2, permissoes)

    with TestClient(main.app) as c:
        yield c, como
    main.app.dependency_overrides.clear()


def test_quem_tem_rebanho_enxerga_a_lista_de_lotes(cliente):
    c, como = cliente
    como("rebanho")
    r = c.get("/lotes/")
    assert r.status_code == 200
    assert [l["rotulo"] for l in r.json()] == ["04 - Pós-parto/Tratamento"]


def test_quem_so_tem_producao_ou_alimentacao_tambem_enxerga(cliente):
    c, como = cliente
    for modulo in ("producao", "alimentacao", "lancamentos", "sanidade"):
        como(modulo)
        assert c.get("/lotes/").status_code == 200, modulo


def test_sem_nenhum_modulo_que_use_lote_continua_barrado(cliente):
    c, como = cliente
    como("financeiro,estoque")
    assert c.get("/lotes/").status_code == 403


def test_rebanho_nao_cadastra_nem_edita_lote(cliente):
    c, como = cliente
    como("rebanho")
    assert c.post("/lotes/", json={"codigo": "09", "nome": "Novo"}).status_code == 403
    assert c.put("/lotes/1", json={"codigo": "04", "nome": "Outro"}).status_code == 403
