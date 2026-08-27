"""
Ajuste urgente (23/07): quando a próxima aplicação de BST cai exatamente na
data de referência, ela deve (1) permanecer no dia — antes, o "<=" do avanço
de ciclo empurrava a data de hoje para a janela seguinte e ela sumia da
Agenda — e (2) gerar um compromisso cronológico (`eventos`) nesse dia, com as
listas de animais já embutidas para abrir sem outra chamada.
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


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        for item in DEFINICOES:
            s.add(ParametroFazenda(
                chave=item["chave"], grupo=item["grupo"], label=item["label"],
                valor=str(item["valor"]), tipo=item.get("tipo", "int"), unidade=item.get("unidade"),
            ))
        # Apta ao BST (grupo lactante, DEL alto o bastante).
        s.add(Animal(numero="300", grupo_primario="01 - Alta", del_dias=70, sexo="F", ativo=True))
        # Lactante mas fora dos critérios de elegibilidade -> entra em excluídos.
        s.add(Animal(numero="301", grupo_primario="02 - Media", del_dias=5, sexo="F", ativo=True))
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
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _lancar_bst(engine, numero: str, data_aplicacao: date):
    with Session(engine) as s:
        s.add(Sanidade(numero_matriz=numero, atividade="BST", data_aplicacao=data_aplicacao, produto="Lactotropin"))
        s.commit()


class TestProximaAplicacaoNoDia:
    def test_permanece_hoje_quando_cai_exatamente_hoje(self, client):
        c, engine = client
        hoje = date.today()
        # intervalo padrão = 12 dias -> última aplicação 12 dias atrás cai hoje.
        _lancar_bst(engine, "300", hoje - timedelta(days=12))
        r = c.get("/agenda/", params={"data": hoje.isoformat()})
        assert r.json()["proxima_visita_bst"] == hoje.isoformat()

    def test_gera_compromisso_na_agenda_do_dia(self, client):
        c, engine = client
        hoje = date.today()
        _lancar_bst(engine, "300", hoje - timedelta(days=12))
        r = c.get("/agenda/", params={"data": hoje.isoformat()})
        d = r.json()
        eventos_bst = [e for e in d["eventos"] if e.get("tipo") == "bst_aplicacao"]
        assert len(eventos_bst) == 1
        ev = eventos_bst[0]
        assert ev["data"] == hoje.isoformat()
        assert ev["categoria"] == "Reprodutivo"
        assert "300" in ev["aptas"] or "300" in ev["incluir_proximo"]
        assert isinstance(ev["inaptas"], list)

    def test_gera_compromisso_com_antecedencia_quando_a_data_ainda_nao_chegou(self, client):
        """
        Antes o compromisso só era gerado quando a data de REFERÊNCIA da
        consulta (`data=`) caía exatamente no dia da próxima aplicação — como
        o front sempre consulta com `data=hoje` (não há navegação de UI que
        troque essa referência), o card nunca aparecia com antecedência,
        mesmo que o usuário navegasse até o dia certo pela grade do
        calendário (ver test_bst_evento_agenda.py para o cenário completo).
        Agora o evento é gerado com a data REAL da próxima aplicação, mesmo
        consultado antes dela chegar.
        """
        c, engine = client
        hoje = date.today()
        # Última aplicação recente -> próxima aplicação está no futuro, não hoje.
        _lancar_bst(engine, "300", hoje - timedelta(days=3))
        proxima = hoje - timedelta(days=3) + timedelta(days=12)
        r = c.get("/agenda/", params={"data": hoje.isoformat()})
        eventos_bst = [e for e in r.json()["eventos"] if e.get("tipo") == "bst_aplicacao"]
        assert len(eventos_bst) == 1
        assert eventos_bst[0]["data"] == proxima.isoformat()
