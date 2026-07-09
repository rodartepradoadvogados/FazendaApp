"""
Testes de permissão na Agenda: se o usuário não tem acesso a um módulo, nada
daquele assunto aparece — nem eventos daquela categoria, nem contas a pagar,
nem os painéis reprodutivos (candidatas IATF, BST).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import AgendaManual, ContaGerencial


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


class _FakeOperadorSoFinanceiro:
    id = 2
    papel = "operador"
    permissoes = "agenda,financeiro"
    ativo = True
    username = "operador_financeiro"


class _FakeOperadorSemFinanceiro:
    id = 3
    papel = "operador"
    permissoes = "agenda,sanidade"
    ativo = True
    username = "operador_sanidade"


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with Session(engine) as s:
        s.add(AgendaManual(data_evento=date.today(), descricao="Reunião com veterinário", categoria="Atividades"))
        s.add(ContaGerencial(
            numero_lancamento="LC-2026-00001", descricao="Conta teste", tipo="despesa",
            data_vencimento=date.today() + timedelta(days=2), valor_total=100.0, origem="manual",
        ))
        s.commit()

    yield main.app
    main.app.dependency_overrides.clear()


def _client_as(app, user):
    from fazenda.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestPermissaoAgenda:
    def test_admin_ve_conta_a_pagar(self, setup):
        c = _client_as(setup, _FakeAdmin())
        r = c.get("/agenda/")
        assert r.json()["totais"]["contas_a_pagar"] == 1
        assert any(e["categoria"] == "Gestão/Financeiro" for e in r.json()["eventos"])

    def test_operador_sem_financeiro_nao_ve_conta_a_pagar(self, setup):
        c = _client_as(setup, _FakeOperadorSemFinanceiro())
        r = c.get("/agenda/")
        d = r.json()
        assert d["contas_a_pagar"] == []
        assert d["totais"]["contas_a_pagar"] == 0
        assert not any(e["categoria"] == "Gestão/Financeiro" for e in d["eventos"])

    def test_operador_com_financeiro_ve_conta_a_pagar(self, setup):
        c = _client_as(setup, _FakeOperadorSoFinanceiro())
        r = c.get("/agenda/")
        d = r.json()
        assert d["totais"]["contas_a_pagar"] == 1
        assert any(e["categoria"] == "Gestão/Financeiro" for e in d["eventos"])

    def test_operador_sem_reproducao_nao_ve_painel_iatf_nem_bst(self, setup):
        c = _client_as(setup, _FakeOperadorSemFinanceiro())
        r = c.get("/agenda/")
        d = r.json()
        assert d["candidatas_iatf"] == []
        assert d["bst_elegiveis"] == []
        assert d["bst_excluidos"] == []
        assert d["totais"]["candidatas_iatf"] == 0

    def test_evento_atividades_sempre_visivel_com_acesso_a_agenda(self, setup):
        c = _client_as(setup, _FakeOperadorSemFinanceiro())
        r = c.get("/agenda/")
        assert any(e["categoria"] == "Atividades" for e in r.json()["eventos"])

    def test_totais_eventos_reflete_apenas_visiveis(self, setup):
        c = _client_as(setup, _FakeOperadorSemFinanceiro())
        r = c.get("/agenda/")
        d = r.json()
        assert d["totais"]["eventos"] == len(d["eventos"])
