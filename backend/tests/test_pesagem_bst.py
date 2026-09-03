"""
Pesagem do rebanho (agendamento por fase) + BST ancorada na última aplicação
+ filtro de medicamentos por doença.

Cobre a batelada de revisão/funcionalidades:
- ocorrencias_pesagem: cadência ancorada no dia da semana (15/15 dias às terças).
- Agenda: cada fase ativa gera um evento `pesagem_rebanho` na data agendada,
  contando só os animais da faixa de idade-alvo.
- proxima_visita_bst: 12 dias após a APLICAÇÃO de BST mais recente (não o serviço).
- /estoque/medicamentos?doenca=…: abre só os medicamentos ligados à doença.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    Animal, AgendamentoPesagem, Doenca, Estoque, PrincipioAtivo, Sanidade, Servico,
)
from fazenda.rules.pesagem_agenda import ocorrencias_pesagem


# --- Unidade: geração de ocorrências ----------------------------------------

class TestOcorrenciasPesagem:
    def test_quinzenal_ancora_na_terca(self):
        # Referência numa terça (2026-07-07); 15 em 15 dias, terça (dia_semana=1).
        datas = ocorrencias_pesagem(
            data_referencia=date(2026, 7, 7), frequencia_valor=15, frequencia_unidade="dias",
            dia_semana=1, ini=date(2026, 7, 1), fim=date(2026, 8, 10),
        )
        assert date(2026, 7, 7) in datas
        assert date(2026, 7, 21) in datas
        assert date(2026, 8, 4) in datas
        # Todas caem numa terça-feira.
        assert all(d.weekday() == 1 for d in datas)

    def test_mensal_ancora_na_terca(self):
        datas = ocorrencias_pesagem(
            data_referencia=date(2026, 7, 7), frequencia_valor=1, frequencia_unidade="meses",
            dia_semana=1, ini=date(2026, 7, 1), fim=date(2026, 10, 1),
        )
        assert all(d.weekday() == 1 for d in datas)
        # ~mensal: uma ocorrência por mês na janela (jul, ago, set).
        assert len({d.month for d in datas}) >= 3

    def test_janela_estreita_pode_nao_ter_ocorrencia(self):
        datas = ocorrencias_pesagem(
            data_referencia=date(2026, 7, 7), frequencia_valor=15, frequencia_unidade="dias",
            dia_semana=1, ini=date(2026, 7, 8), fim=date(2026, 7, 12),
        )
        assert datas == []


# --- Integração: agenda + BST + medicamentos por doença ---------------------

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

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
        with Session(engine) as s:
            # Bezerras com nascimento recente (idade 0–90 dias em 07/07).
            s.add(Animal(numero="101", data_nasc=date(2026, 6, 1), sexo="F", ativo=True))
            s.add(Animal(numero="102", data_nasc=date(2026, 6, 15), sexo="F", ativo=True))
            # Adulta fora da faixa (não deve contar na pesagem de bezerras).
            s.add(Animal(numero="200", data_nasc=date(2022, 1, 1), sexo="F", ativo=True))
            # Fase de pesagem: bezerras 0–90 dias, 15/15 dias, terça, ref 07/07.
            s.add(AgendamentoPesagem(
                nome="Bezerras até desmama", ativo=True, idade_min_dias=0, idade_max_dias=90,
                frequencia_valor=15, frequencia_unidade="dias", dia_semana=1,
                data_referencia=date(2026, 7, 7),
            ))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestAgendaPesagem:
    def test_evento_pesagem_na_terca(self, client):
        r = client.get("/agenda/", params={"data": "2026-07-07", "dias": 10})
        eventos = r.json()["eventos"]
        pes = [e for e in eventos if e.get("tipo") == "pesagem_rebanho"]
        assert len(pes) == 1
        ev = pes[0]
        assert ev["data"] == "2026-07-07"
        # Só as duas bezerras da faixa entram (a adulta 200 fica de fora).
        assert sorted(ev["animais"]) == ["101", "102"]
        assert "Bezerras até desmama" in ev["descricao"]

    def test_pesagem_marcada_realizada_some(self, client):
        chave = "pesagem_1_2026-07-07"
        client.post("/agenda/realizados", json={"evento_id": chave})
        r = client.get("/agenda/", params={"data": "2026-07-07", "dias": 10})
        assert not any(e.get("id") == chave for e in r.json()["eventos"])


class TestBstUltimaAplicacao:
    def test_bst_12_dias_apos_ultima_aplicacao(self, client):
        # Aplica BST de ROTINA (atividade="BST") em duas datas; a próxima
        # visita = mais recente + 12 dias. (atividade="BST" é o que
        # diferencia a rotina de indução de lactação/avulso — ver
        # test_bst_ancora_rotina.py.)
        client_session_add(client, Sanidade(numero_matriz="200", data_aplicacao=date(2026, 7, 1), produto="Lactotropin 500", atividade="BST"))
        client_session_add(client, Sanidade(numero_matriz="200", data_aplicacao=date(2026, 7, 5), produto="Boostin", atividade="BST"))
        r = client.get("/agenda/", params={"data": "2026-07-06"})
        assert r.json()["proxima_visita_bst"] == "2026-07-17"  # 05/07 + 12


class TestMedicamentosPorDoenca:
    def test_filtra_por_doenca(self, client):
        # Doença → princípio ativo → item de estoque.
        d = Doenca(nome="Mastite", ativo=True)
        client_session_add(client, d)
        pa = PrincipioAtivo(nome="Cefquinoma", ativo=True, doenca_id=_last_id(client, Doenca))
        client_session_add(client, pa)
        client_session_add(client, Estoque(nome="Cobactan", principio_ativo_id=_last_id(client, PrincipioAtivo)))
        client_session_add(client, Estoque(nome="Item sem doença"))
        r = client.get("/estoque/medicamentos", params={"doenca": "Mastite"})
        nomes = [m["nome"] for m in r.json()]
        assert "Cobactan" in nomes
        assert "Item sem doença" not in nomes


# Helpers — inserem direto na sessão do engine de teste via override.
def _engine_session(client):
    override = client.app.dependency_overrides[database.get_session]
    gen = override()
    return gen, next(gen)


def client_session_add(client, obj):
    gen, s = _engine_session(client)
    s.add(obj)
    s.commit()
    try:
        next(gen)
    except StopIteration:
        pass


def _last_id(client, model):
    from sqlmodel import select
    gen, s = _engine_session(client)
    rows = s.exec(select(model)).all()
    val = rows[-1].id
    try:
        next(gen)
    except StopIteration:
        pass
    return val
