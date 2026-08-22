"""
Endpoint `POST /reproducao/agenda-reprodutiva/card` — o card configurável que
substitui os cards fixos da Agenda Reprodutiva (situação reprodutiva ao
vivo). Testa a fiação completa (banco -> estados_ao_vivo -> avaliar_card),
não a lógica de filtro em si (já coberta em
test_agenda_reprodutiva_configuravel.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ParametroFazenda, Parto, PesagemCorporal, Servico

HOJE = date(2026, 7, 8)
IDADE_APTA_DIAS = 457  # 15 meses — default de idade_apta_min_meses


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # `fazenda.rules.parametros._linha` abre sessão própria via
    # `fazenda.database.engine` (não pela dependência `get_session`) —
    # sem este monkeypatch, `_set_parametro` grava num banco e `get_param`
    # lê de outro, e a sobrescrita nunca aparece na resposta do endpoint.
    monkeypatch.setattr(database, "engine", engine)

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


def _add_animal(engine, numero, categoria_abrev, idade_dias=None, grupo_primario=None, a_descartar=False):
    with Session(engine) as s:
        s.add(Animal(
            numero=numero, categoria_abrev=categoria_abrev, sexo="F",
            data_nasc=(HOJE - timedelta(days=idade_dias)) if idade_dias is not None else None,
            grupo_primario=grupo_primario, a_descartar=a_descartar, ativo=True,
        ))
        s.commit()


def _add_peso(engine, numero, peso, dias_atras=0):
    with Session(engine) as s:
        s.add(PesagemCorporal(numero_matriz=numero, data_pesagem=HOJE - timedelta(days=dias_atras), peso_kg=peso))
        s.commit()


def _add_servico(engine, numero, dias_atras, **kwargs):
    with Session(engine) as s:
        s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), **kwargs))
        s.commit()


def _add_parto(engine, numero, dias_atras):
    with Session(engine) as s:
        s.add(Parto(numero_matriz=numero, data_parto=HOJE - timedelta(days=dias_atras), ordem_parto=1))
        s.commit()


def _set_parametro(engine, chave, valor):
    with Session(engine) as s:
        s.add(ParametroFazenda(
            chave=chave, fazenda_id=None, grupo="metas_reproducao", label=chave, valor=str(valor), tipo="int",
        ))
        s.commit()


def _card(c, **body):
    return c.post("/reproducao/agenda-reprodutiva/card", params={"data": HOJE.isoformat()}, json=body)


class TestSituacaoInvalida:
    def test_422_em_situacao_desconhecida(self, client):
        c, _ = client
        r = _card(c, situacao="inexistente")
        assert r.status_code == 422


class TestPev:
    def test_vaca_recem_parida_entra_em_pev(self, client):
        c, engine = client
        _add_animal(engine, "1", "Vaca", idade_dias=2000, grupo_primario="Lote 1")
        _add_parto(engine, "1", 10)
        r = _card(c, situacao="pev")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["itens"][0]["numero_matriz"] == "1"
        assert body["itens"][0]["del_dias"] == 10

    def test_periodo_filtra_por_dias_desde_o_parto(self, client):
        c, engine = client
        _add_animal(engine, "1", "Vaca", idade_dias=2000)
        _add_parto(engine, "1", 40)
        r = _card(c, situacao="pev", periodos=[[0, 10]])
        assert r.json()["total"] == 0
        r2 = _card(c, situacao="pev", periodos=[[30, 44]])
        assert r2.json()["total"] == 1


class TestInseminada:
    def test_periodos_multiplos_cobrem_os_3_cortes_antigos_num_card_so(self, client):
        c, engine = client
        _add_animal(engine, "1", "Vaca", idade_dias=2000)
        _add_animal(engine, "2", "Vaca", idade_dias=2000)
        _add_servico(engine, "1", 10)
        _add_servico(engine, "2", 70)
        r = _card(c, situacao="inseminada", periodos=[[1, 29], [60, 999]])
        assert r.json()["total"] == 2
        assert {i["numero_matriz"] for i in r.json()["itens"]} == {"1", "2"}


class TestVaziaAtrasada:
    # Idade dentro da janela apta (457 a 487 dias) — nunca bate o teto de
    # idade sozinho. Peso cruzou o mínimo bem antes (300 dias atrás, quando
    # ela ainda nem tinha a idade), então quem decide "data em que ficou
    # apta" aqui é a IDADE, não o peso: ela ficou apta há exatamente
    # (idade_dias - 457) dias.
    IDADE_DIAS = 470  # ficou apta há 470 - 457 = 13 dias

    def test_novilha_atrasada_por_dias_apos_aptidao(self, client):
        """Com o parâmetro reduzido para 10 dias (< 13), o card
        "vazia_atrasada" já pega ela pelo novo gatilho — mesmo sem chegar
        perto do teto de idade (487) — ponta a ponta desde o banco."""
        c, engine = client
        _set_parametro(engine, "dias_atraso_apos_aptidao_novilha", 10)
        _add_animal(engine, "1", "Novilha", idade_dias=self.IDADE_DIAS)
        _add_peso(engine, "1", 320.0, dias_atras=300)
        r = _card(c, situacao="vazia_atrasada")
        assert r.json()["total"] == 1
        assert r.json()["itens"][0]["numero_matriz"] == "1"

    def test_dentro_do_parametro_padrao_ainda_nao_e_atrasada(self, client):
        """Sem sobrescrever o parâmetro (padrão de 30 dias), 13 dias desde
        que ficou apta não é atraso ainda."""
        c, engine = client
        _add_animal(engine, "1", "Novilha", idade_dias=self.IDADE_DIAS)
        _add_peso(engine, "1", 320.0, dias_atras=300)
        r = _card(c, situacao="vazia_atrasada")
        assert r.json()["total"] == 0

    def test_sem_pesagem_nao_dispara_o_novo_gatilho(self, client):
        c, engine = client
        _set_parametro(engine, "dias_atraso_apos_aptidao_novilha", 10)
        _add_animal(engine, "1", "Novilha", idade_dias=self.IDADE_DIAS)
        r = _card(c, situacao="vazia_atrasada")
        assert r.json()["total"] == 0


class TestADescartar:
    def test_puxa_so_quem_esta_marcado(self, client):
        c, engine = client
        _add_animal(engine, "1", "Vaca", idade_dias=2000, a_descartar=True)
        _add_animal(engine, "2", "Vaca", idade_dias=2000, a_descartar=False)
        r = _card(c, situacao="a_descartar")
        assert r.json()["total"] == 1
        assert r.json()["itens"][0]["numero_matriz"] == "1"

    def test_marcado_a_descartar_some_de_outras_situacoes(self, client):
        c, engine = client
        _add_animal(engine, "1", "Vaca", idade_dias=2000, a_descartar=True)
        _add_parto(engine, "1", 10)
        r = _card(c, situacao="pev")
        assert r.json()["total"] == 0


class TestEixoLoteECategoria:
    def test_filtra_por_lote_e_categoria_juntos(self, client):
        c, engine = client
        _add_animal(engine, "1", "Vaca", idade_dias=2000, grupo_primario="Lote 1")
        _add_animal(engine, "2", "Vaca", idade_dias=2000, grupo_primario="Lote 9")
        _add_animal(engine, "3", "Novilha", idade_dias=500, grupo_primario="Lote 1")
        _add_parto(engine, "1", 10)
        _add_parto(engine, "2", 10)
        r = _card(c, situacao="pev", categoria="vaca", lotes=["Lote 1"])
        assert r.json()["total"] == 1
        assert r.json()["itens"][0]["numero_matriz"] == "1"
