"""
Regressão: a "próxima aplicação de BST" (âncora real, `proxima_visita_bst`)
precisa aparecer na Agenda como um evento acionável/gerencial
(`tipo == "bst_aplicacao"`), não só como um número informativo no JSON —
e precisa aparecer ANTES do dia da aplicação, não só nele.

Cenário relatado pelo usuário em produção: rotina do rebanho inteiro em
16/08/2026 com intervalo_bst=12 -> próxima aplicação em 28/08/2026. A data
já saía certa em `proxima_visita_bst`, mas o card não aparecia na Agenda —
causa raiz real (confirmada por este teste antes da correção): o evento só
era gerado quando a data de REFERÊNCIA da consulta (`GET /agenda/?data=`)
era exatamente igual à data da próxima aplicação. Como o front SEMPRE
consulta a Agenda com `data=hoje` (não existe navegação de UI que troque
essa referência — a visão de calendário/linha do tempo só filtram no
cliente uma única resposta já carregada, ver frontend/app/agenda/page.tsx),
o card nunca aparecia enquanto a data da próxima aplicação ainda não tivesse
chegado, mesmo navegando até ela pela grade do calendário.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ParametroFazenda, Sanidade
from fazenda.rules.parametros import DEFINICOES

INTERVALO_BST = 12
DATA_ROTINA = date(2026, 8, 16)
DATA_PROXIMA = DATA_ROTINA + timedelta(days=INTERVALO_BST)  # 2026-08-28


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # `intervalo_bst()`/`get_param` leem direto de `fazenda.database.engine`,
    # não da sessão injetada — precisa apontar pro engine de teste (mesmo
    # padrão de test_bst_ancora_rotina.py).
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        for item in DEFINICOES:
            valor = INTERVALO_BST if item["chave"] == "intervalo_bst" else item["valor"]
            s.add(ParametroFazenda(
                chave=item["chave"], grupo=item["grupo"], label=item["label"],
                valor=str(valor), tipo=item.get("tipo", "int"), unidade=item.get("unidade"),
            ))
        for numero in ["1", "2", "3"]:
            s.add(Animal(numero=numero, grupo_primario="01 - Alta", del_dias=70, sexo="F", ativo=True))
        s.add(Sanidade(
            numero_matriz="1", atividade="BST", data_aplicacao=DATA_ROTINA, produto="Lactotropin",
        ))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _agenda(c, data: date) -> dict:
    r = c.get("/agenda/", params={"data": data.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


class TestEventoBstAplicacaoNaAgenda:
    def test_data_informativa_bate_com_a_esperada(self, client):
        c, _ = client
        agenda = _agenda(c, DATA_ROTINA)
        assert agenda["proxima_visita_bst"] == DATA_PROXIMA.isoformat()

    def test_evento_acionavel_aparece_consultando_no_dia_da_aplicacao(self, client):
        c, _ = client
        agenda = _agenda(c, DATA_PROXIMA)
        eventos_bst = [e for e in agenda["eventos"] if e.get("tipo") == "bst_aplicacao"]
        assert len(eventos_bst) == 1, agenda["eventos"]
        evento = eventos_bst[0]
        assert evento["data"] == DATA_PROXIMA.isoformat()
        assert evento["categoria"] == "Reprodutivo"

    def test_evento_acionavel_ja_aparece_com_antecedencia(self, client):
        """
        Cenário exato do bug relatado: consultando a Agenda ANTES do dia da
        aplicação (como o front sempre faz, com `data=hoje`) o card precisa
        aparecer mesmo assim — já carregando a data real da aplicação, para
        que a linha do tempo/calendário consiga colocá-lo no dia certo.
        """
        c, _ = client
        agenda = _agenda(c, DATA_ROTINA)  # consulta no dia da rotina, 12 dias antes
        eventos_bst = [e for e in agenda["eventos"] if e.get("tipo") == "bst_aplicacao"]
        assert len(eventos_bst) == 1, agenda["eventos"]
        assert eventos_bst[0]["data"] == DATA_PROXIMA.isoformat()

    def test_evento_some_apos_marcado_como_realizado(self, client):
        c, _ = client
        agenda = _agenda(c, DATA_ROTINA)
        evento_id = next(e["id"] for e in agenda["eventos"] if e.get("tipo") == "bst_aplicacao")
        r = c.post("/agenda/realizados", json={"evento_id": evento_id})
        assert r.status_code == 200, r.text
        agenda = _agenda(c, DATA_ROTINA)
        eventos_bst = [e for e in agenda["eventos"] if e.get("tipo") == "bst_aplicacao"]
        assert eventos_bst == []
