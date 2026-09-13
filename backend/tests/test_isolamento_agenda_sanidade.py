"""
Isolamento por fazenda — Sanidade criada a partir da Agenda (gauntlet A-1).

Bug real: confirmar uma aplicação programada ("dar baixa") pela Agenda
criava o registro de Sanidade sem `fazenda_id` — a listagem de
GET /sanidade/aplicacoes filtra estritamente por fazenda_id, então a
aplicação confirmada sumia da tela (e do cálculo de carência de leite) tanto
para quem confirmou quanto para qualquer outra fazenda. Cobre os dois
caminhos mais usados no dia a dia: aplicação agendada avulsa e vacina
pré-parto (ambos passam por `_baixar_aplicacao_agendada`/
`_baixar_vacina_pre_parto` em fazenda/api/routers/agenda.py). Os outros 3
pontos corrigidos (protocolo sanitário, protocolo IATF, indução de
lactação) usam o mesmo padrão — não replicados aqui por exigirem cadastro
de lançamento/etapa mais elaborado.

Self-contained: fixture `client` própria (mesmo padrão de
test_isolamento_sanidade.py), banco isolado por teste.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import AplicacaoAgendada, ContratoFazenda, ContratoFazendaModulo, Fazenda, Sanidade
from fazenda.models.planos import MODULOS_COMERCIAIS

HOJE = date.today()


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))

        s.add(AplicacaoAgendada(id=1, numero_matriz="9001", data=HOJE, produto="Ivomec", fazenda_id=1))
        s.add(AplicacaoAgendada(
            id=2, numero_matriz="9002", data=HOJE, produto="Vacina pré-parto",
            via="Subcutânea", observacao="Vacina pré-parto", fazenda_id=1,
        ))
        s.commit()

    def _get_session_override():
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

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestAplicacaoAgendadaGravaFazendaId:
    def test_confirmar_aplicacao_agendada_grava_fazenda_id(self, client):
        c, engine = client
        r = c.post("/agenda/realizados", json={"evento_id": "aplic_agendada_1"})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            sanidade = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "9001")).first()
            assert sanidade is not None
            assert sanidade.fazenda_id == 1

        # Some do que já foi confirmado deve continuar aparecendo pra fazenda
        # DONA da aplicação — era exatamente isso que o bug quebrava.
        r = c.get("/sanidade/aplicacoes")
        produtos = {item["produto"] for item in r.json()["aplicacoes"]}
        assert "Ivomec" in produtos

    def test_confirmar_vacina_pre_parto_grava_fazenda_id(self, client):
        c, engine = client
        r = c.post("/agenda/realizados", json={"evento_id": "vacina_pre_parto_9002_" + HOJE.isoformat()})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            sanidade = s.exec(select(Sanidade).where(Sanidade.numero_matriz == "9002")).first()
            assert sanidade is not None
            assert sanidade.fazenda_id == 1
