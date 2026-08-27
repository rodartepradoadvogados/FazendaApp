"""
Fecha o gap descrito em `fazenda/rules/lactacao.py::ORIGEM_INDUCAO`: o modelo
`Lactacao` e `abrir_lactacao(origem="inducao")` já existiam prontos, mas
nenhum call site os usava — uma matriz que terminava um protocolo de indução
de lactação (`ProtocoloInducaoLancamento`/`ProtocoloInducaoAplicacao`, em
lote) ficava com todas as etapas realizadas e NUNCA entrava em lactação no
sistema (o caso relatado foi a matriz 422 — usada aqui de propósito).

As aplicações são marcadas `realizada=True` diretamente no banco (em vez de
percorrer o fluxo completo de `/agenda/realizados` do protocolo de indução,
já coberto por outros testes) — isolando o que este arquivo cobre: o NOVO
bloco de agenda (`eventos_confirmar_lactacao_inducao`) e o NOVO endpoint de
confirmação, dado um estado de aplicações já concluído.

Cobre:
  1. Protocolo 100% concluído + sem Lactacao aberta -> aparece o card
     "confirmar_lactacao_inducao" na Agenda (o cenário da matriz 422).
  2. Protocolo com alguma etapa pendente -> NÃO aparece.
  3. Matriz já em lactação (ex.: parto lançado depois) -> NÃO aparece mesmo
     com o protocolo 100% concluído.
  4. Confirmar "Sim" abre a Lactacao com origem="inducao" na data esperada e
     sincroniza Animal.del_dias.
  5. Depois de confirmado (Sim ou Não) + marcarEventoRealizado, o card não
     reaparece numa chamada seguinte de /agenda/.
  6. Lançamento com 2 matrizes, só uma concluída -> só ela vira pendência.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Lactacao, ProtocoloInducaoAplicacao


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _protocolo_id(c) -> int:
    r = c.post("/cadastro/protocolos-inducao-lactacao", json={
        "nome": "Indução padrão — teste",
        "dia_inicial": 0,
        "etapas": [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 5, "unidade": "ml"},
            {"dia": 6, "tipo": "manejo", "produto": "Iniciar ordenha"},
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _lancar(c, protocolo_id: int, animais: list[str], data_d0: str) -> int:
    r = c.post("/producao/inducao-lactacao", json={
        "protocolo_id": protocolo_id, "animais": animais, "data_d0": data_d0,
    })
    assert r.status_code == 201, r.text
    return r.json()["lancamento_id"]


def _concluir_etapas(engine, lancamento_id: int, numeros_matriz: list[str], apenas_dias: set[int] | None = None):
    """Marca `realizada=True` diretamente no banco — as etapas do(s) dia(s)
    informado(s) (todos, por padrão) das matrizes informadas."""
    with Session(engine) as s:
        query = (
            select(ProtocoloInducaoAplicacao)
            .where(ProtocoloInducaoAplicacao.lancamento_id == lancamento_id)
            .where(ProtocoloInducaoAplicacao.numero_matriz.in_(numeros_matriz))
        )
        aps = s.exec(query).all()
        for a in aps:
            if apenas_dias is not None and a.dia not in apenas_dias:
                continue
            a.realizada = True
            a.data_realizacao = a.data_prevista
            s.add(a)
        s.commit()


def _eventos_confirmar(resposta_json: dict) -> list[dict]:
    return [e for e in resposta_json["eventos"] if e.get("tipo") == "confirmar_lactacao_inducao"]


def _agenda(c) -> dict:
    return c.get("/agenda/", params={"data": date.today().isoformat(), "dias": 5}).json()


class TestApareceQuandoConcluidoSemLactacao:
    def test_matriz_422_concluida_sem_lactacao_gera_pendencia(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["422"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["422"])

        eventos = _eventos_confirmar(_agenda(c))
        assert len(eventos) == 1, eventos
        evento = eventos[0]
        assert evento["numero_animal"] == "422"
        assert evento["lancamento_id"] == lancamento_id
        assert evento["numero_matriz"] == "422"
        assert evento["data_sugerida"] is not None

    def test_protocolo_incompleto_nao_gera_pendencia(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["500"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["500"], apenas_dias={0})  # falta o D6

        assert _eventos_confirmar(_agenda(c)) == []

    def test_matriz_ja_em_lactacao_nao_gera_pendencia(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["600"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["600"])

        # Confirma "Sim" — abre a lactação. Depois disso não deveria mais
        # pedir confirmação (mesmo sem marcar o evento como realizado).
        r = c.post(f"/producao/inducao-lactacao/{lancamento_id}/600/confirmar", json={"entrou_em_lactacao": True})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            assert s.exec(select(Lactacao).where(Lactacao.numero_matriz == "600")).first() is not None

        assert _eventos_confirmar(_agenda(c)) == []


class TestLactacaoFantasmaAnteriorAInducao:
    """O caso real que motivou este ajuste (matriz 422, relatado em produção):
    uma secagem que nunca foi lançada no sistema deixa a `Lactacao` anterior
    aberta para sempre. Sem este ajuste, o card via `lactacao_aberta(...) is
    not None` e desistia calado — a matriz ficava com DEL vivo crescendo
    (497 dias, no caso real) e sem NENHUM jeito de abrir a lactação da
    indução, porque o próprio código achava que ela "já estava lactando".

    Diferença do critério: a lactação aberta PREVIA ao D0 da indução é tratada
    como o furo, não como "já resolvido" — o card aparece do mesmo jeito, com
    `aviso`, e "Sim" fecha a lactação antiga (comportamento já embutido em
    `abrir_lactacao`) na data escolhida para a nova."""

    def test_lactacao_aberta_antes_do_d0_gera_pendencia_com_aviso(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["422"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["422"])

        data_lactacao_antiga = date.today() - timedelta(days=497)
        with Session(engine) as s:
            s.add(Lactacao(numero_matriz="422", data_inicio=data_lactacao_antiga, origem="parto"))
            s.commit()

        eventos = _eventos_confirmar(_agenda(c))
        assert len(eventos) == 1, eventos
        assert eventos[0]["aviso"] is not None
        assert data_lactacao_antiga.isoformat() in eventos[0]["aviso"]

    def test_confirmar_sim_fecha_lactacao_antiga_na_data_da_nova(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["422"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["422"])

        data_lactacao_antiga = date.today() - timedelta(days=497)
        with Session(engine) as s:
            antiga = Lactacao(numero_matriz="422", data_inicio=data_lactacao_antiga, origem="parto")
            s.add(antiga)
            s.commit()
            antiga_id = antiga.id

        data_nova = (date.today() - timedelta(days=1)).isoformat()
        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/422/confirmar",
            json={"entrou_em_lactacao": True, "data_inicio": data_nova},
        )
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            antiga_depois = s.get(Lactacao, antiga_id)
            assert antiga_depois.data_fim.isoformat() == data_nova

            nova = s.exec(
                select(Lactacao).where(Lactacao.numero_matriz == "422", Lactacao.id != antiga_id)
            ).first()
            assert nova is not None
            assert nova.origem == "inducao"
            assert nova.data_fim is None

        assert _eventos_confirmar(_agenda(c)) == []


class TestConfirmarEndpoint:
    def test_confirmar_sim_abre_lactacao_origem_inducao_e_sincroniza_del(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["422"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["422"])

        with Session(engine) as s:
            s.add(Animal(numero="422", sexo="F", ativo=True))
            s.commit()

        eventos = _eventos_confirmar(_agenda(c))
        data_sugerida = eventos[0]["data_sugerida"]

        r = c.post(f"/producao/inducao-lactacao/{lancamento_id}/422/confirmar", json={"entrou_em_lactacao": True})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["entrou_em_lactacao"] is True
        assert corpo["lactacao_id"] is not None

        with Session(engine) as s:
            lact = s.get(Lactacao, corpo["lactacao_id"])
            assert lact.numero_matriz == "422"
            assert lact.origem == "inducao"
            assert lact.data_inicio.isoformat() == data_sugerida
            assert lact.data_fim is None

            animal = s.exec(select(Animal).where(Animal.numero == "422")).first()
            assert animal.del_dias is not None

    def test_confirmar_sim_aceita_override_de_data_inicio(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["777"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["777"])

        data_escolhida = (date.today() - timedelta(days=1)).isoformat()
        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/777/confirmar",
            json={"entrou_em_lactacao": True, "data_inicio": data_escolhida},
        )
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            lact = s.exec(select(Lactacao).where(Lactacao.numero_matriz == "777")).first()
            assert lact.data_inicio.isoformat() == data_escolhida

    def test_confirmar_nao_nao_abre_lactacao(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["888"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["888"])

        r = c.post(f"/producao/inducao-lactacao/{lancamento_id}/888/confirmar", json={"entrou_em_lactacao": False})
        assert r.status_code == 200, r.text
        assert r.json() == {"entrou_em_lactacao": False, "lactacao_id": None}

        with Session(engine) as s:
            assert s.exec(select(Lactacao).where(Lactacao.numero_matriz == "888")).first() is None

    def test_lancamento_inexistente_da_404(self, client):
        c, engine = client
        r = c.post("/producao/inducao-lactacao/999999/422/confirmar", json={"entrou_em_lactacao": True})
        assert r.status_code == 404


class TestNaoReaparecerAposResposta:
    @pytest.mark.parametrize("entrou_em_lactacao", [True, False])
    def test_evento_nao_reaparece_apos_marcar_realizado(self, client, entrou_em_lactacao):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["333"], data_d0)
        _concluir_etapas(engine, lancamento_id, ["333"])

        chave = f"confirmar_lactacao_inducao_{lancamento_id}_333"
        r = c.post(
            f"/producao/inducao-lactacao/{lancamento_id}/333/confirmar",
            json={"entrou_em_lactacao": entrou_em_lactacao},
        )
        assert r.status_code == 200, r.text
        assert c.post("/agenda/realizados", json={"evento_id": chave}).status_code == 200

        assert _eventos_confirmar(_agenda(c)) == []


class TestMultiplasMatrizesNoMesmoLancamento:
    def test_so_a_matriz_concluida_vira_pendencia(self, client):
        c, engine = client
        protocolo_id = _protocolo_id(c)
        data_d0 = (date.today() - timedelta(days=10)).isoformat()
        lancamento_id = _lancar(c, protocolo_id, ["111", "222"], data_d0)
        # Conclui só a 111 — deixa a 222 com etapas pendentes.
        _concluir_etapas(engine, lancamento_id, ["111"])

        eventos = _eventos_confirmar(_agenda(c))
        numeros = {e["numero_animal"] for e in eventos}
        assert numeros == {"111"}, eventos
