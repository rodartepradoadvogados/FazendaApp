"""Painel "Candidatas à próxima IATF" da Agenda (`GET /agenda/`).

Estava descoberto: nenhum teste exercitava o conteúdo do painel, só a
permissão. Estes cobrem os cinco furos que a migração do `sit_rep` congelado
para o estado reprodutivo AO VIVO fechou, mais o caso que motivou a migração.

A Agenda responde "quem trabalho HOJE" — a projeção para a próxima visita é a
tela de Histórico > Ciclos de IATF (ver test_candidatas_iatf_projetadas.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Parto, ProtocoloIatfAplicacao, Servico

HOJE = date.today()


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


def _numeros(c) -> list[str]:
    r = c.get("/agenda/")
    assert r.status_code == 200
    return [x["numero_matriz"] for x in r.json()["candidatas_iatf"]]


def _vaca_apta(s, numero: str, **kw):
    """Vaca com DEL 80: passou do PEV (45) e ainda dentro do DEL máximo para
    1º serviço (100), ou seja, estado APTA."""
    s.add(Animal(numero=numero, sexo="F", ativo=True, **kw))
    s.add(Parto(numero_matriz=numero, data_parto=HOJE - timedelta(days=80), ordem_parto=1))


def test_vaca_apta_aparece(client):
    c, engine = client
    with Session(engine) as s:
        _vaca_apta(s, "1", sit_rep="Vaz. apt.")
        s.commit()
    assert _numeros(c) == ["1"]


def test_dentro_do_pev_nao_aparece_nem_com_diagnostico_negativo(client):
    """O furo mais caro do critério antigo: o ramo do DG negativo não testava
    PEV, então a vaca recém-parida ia para a lista do curral."""
    c, engine = client
    with Session(engine) as s:
        s.add(Animal(numero="2", sexo="F", ativo=True, sit_rep="Vaz. atr."))
        s.add(Parto(numero_matriz="2", data_parto=HOJE - timedelta(days=10), ordem_parto=1))
        s.add(Servico(numero_matriz="2", data_servico=HOJE - timedelta(days=200),
                      diagnostico="NEGATIVO", ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    assert "2" not in _numeros(c)


def test_em_protocolo_iatf_nao_aparece(client):
    """Vaca com D0 aplicado hoje não pode ser oferecida de novo. Depende de a
    Agenda carregar as aplicações SEM o filtro `realizada == False` — a linha de
    D0 já está realizada quando o implante foi colocado."""
    c, engine = client
    with Session(engine) as s:
        _vaca_apta(s, "3", sit_rep="Vaz. apt.")
        s.add(ProtocoloIatfAplicacao(numero_matriz="3", lancamento_id=1, dia=0,
                                     descricao="D0 — implante", realizada=True,
                                     data_prevista=HOJE - timedelta(days=2)))
        s.commit()
    assert "3" not in _numeros(c)


def test_inseminada_aguardando_diagnostico_nao_aparece(client):
    c, engine = client
    with Session(engine) as s:
        _vaca_apta(s, "4", sit_rep="Vaz. atr.")
        s.add(Servico(numero_matriz="4", data_servico=HOJE - timedelta(days=10),
                      ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    assert "4" not in _numeros(c)


def test_marcada_a_descartar_nao_aparece(client):
    """R1 — `classificar_animal` não consulta `a_descartar`; o corte é feito
    pelo motor antes de classificar."""
    c, engine = client
    with Session(engine) as s:
        _vaca_apta(s, "5", sit_rep="Vaz. apt.", a_descartar=True)
        s.commit()
    assert "5" not in _numeros(c)


def test_novilha_sem_idade_nem_peso_nao_aparece(client):
    c, engine = client
    with Session(engine) as s:
        s.add(Animal(numero="6", sexo="F", ativo=True, sit_rep="Vaz. apt."))
        s.commit()
    assert "6" not in _numeros(c)


def test_gestante_pelo_app_sai_mesmo_com_csv_dizendo_vazia(client):
    """O defeito que a migração existe para resolver: o GERAL.csv está velho e
    diz 'Vaz. apt.', mas o diagnóstico positivo já foi lançado no sistema."""
    c, engine = client
    with Session(engine) as s:
        s.add(Animal(numero="7", sexo="F", ativo=True, sit_rep="Vaz. apt."))
        s.add(Parto(numero_matriz="7", data_parto=HOJE - timedelta(days=200), ordem_parto=1))
        s.add(Servico(numero_matriz="7", data_servico=HOJE - timedelta(days=40),
                      diagnostico="POSITIVO", ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    assert "7" not in _numeros(c)


def test_apta_pelo_app_entra_mesmo_com_csv_dizendo_gestante(client):
    """O outro lado do mesmo defeito: pariu pelo app, o CSV ainda diz 'Ges.'."""
    c, engine = client
    with Session(engine) as s:
        _vaca_apta(s, "8", sit_rep="Ges.")
        s.commit()
    assert "8" in _numeros(c)


def test_necessidade_de_hormonio_acompanha_a_lista(client):
    """A lista de compra de implante/hormônio é `len(candidatas)` — mudar o
    critério muda o pedido."""
    c, engine = client
    with Session(engine) as s:
        _vaca_apta(s, "9", sit_rep="Vaz. apt.")
        _vaca_apta(s, "10", sit_rep="Vaz. apt.", a_descartar=True)
        s.commit()
    d = c.get("/agenda/").json()
    assert [x["numero_matriz"] for x in d["candidatas_iatf"]] == ["9"]
    assert d["necessidade_iatf"]["implantes"] == 1, "a descartada não entra no pedido"


def test_pev_encerra_nao_dispara_para_gestante_com_sit_rep_velho(client):
    """O segundo ponto migrado: o alerta "PEV encerra — liberar p/ inseminar"
    excluía gestante por `sit_rep`, então a vaca que engravidasse pelo app
    continuava recebendo o aviso até o próximo CSV."""
    c, engine = client
    with Session(engine) as s:
        s.add(Animal(numero="11", sexo="F", ativo=True, sit_rep="Vaz. pev"))
        s.add(Parto(numero_matriz="11", data_parto=HOJE - timedelta(days=20), ordem_parto=1))
        s.add(Servico(numero_matriz="11", data_servico=HOJE - timedelta(days=10),
                      diagnostico="POSITIVO", ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    eventos = c.get("/agenda/").json()["eventos"]
    assert not [
        e for e in eventos
        if e.get("numero_animal") == "11" and "PEV encerra" in e.get("descricao", "")
    ]


def test_pev_encerra_continua_disparando_para_vazia(client):
    """Contraprova do teste acima: sem gestação, o aviso tem que aparecer."""
    c, engine = client
    with Session(engine) as s:
        s.add(Animal(numero="12", sexo="F", ativo=True, sit_rep="Vaz. pev"))
        s.add(Parto(numero_matriz="12", data_parto=HOJE - timedelta(days=20), ordem_parto=1))
        s.commit()
    eventos = c.get("/agenda/").json()["eventos"]
    assert [
        e for e in eventos
        if e.get("numero_animal") == "12" and "PEV encerra" in e.get("descricao", "")
    ]
