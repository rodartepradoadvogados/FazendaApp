"""Testes de GET /reproducao/protocolo-iatf/candidatas — candidatas à próxima
IATF com projeção de aptidão na data do próximo serviço (usado em
Histórico > Reprodução > Ciclos de IATF)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Parto, Servico


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


def test_apta_hoje_entra_e_e_marcada_como_apta_hoje(client):
    """Vaca passada do PEV (45) e ainda dentro do DEL máximo para 1º serviço
    (100): candidata na visita e já trabalhável hoje."""
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="1", sexo="F", ativo=True, sit_rep="Vaz. apt."))
        s.add(Parto(numero_matriz="1", data_parto=hoje - timedelta(days=80), ordem_parto=1))
        # Ancora a próxima visita: último serviço do rebanho + 21 dias.
        s.add(Servico(numero_matriz="9", data_servico=hoje - timedelta(days=10), ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    assert r.status_code == 200
    cand = next(x for x in r.json()["candidatas"] if x["numero_matriz"] == "1")
    assert cand["motivo"] == "Vazia apta"
    assert cand["estado"] == "apta"
    assert cand["apta_hoje"] is True
    assert cand["apta_na_proxima_visita"] is True
    assert cand["del_dias_projetado"] > cand["del_dias"]


def test_sai_do_pev_ate_a_visita_entra_no_relatorio_mas_nao_esta_apta_hoje(client):
    """A decisão que define esta tela: ela responde 'quem planejo para a
    visita', não 'quem trabalho hoje'. Vaca com DEL 38 hoje e PEV 45 ainda está
    suspensa agora, mas terá DEL ~49 na visita (11 dias à frente) — entra na
    lista, marcada como ainda não apta hoje."""
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="2", sexo="F", ativo=True, sit_rep="Vaz. pev"))
        s.add(Parto(numero_matriz="2", data_parto=hoje - timedelta(days=38), ordem_parto=1))
        s.add(Servico(numero_matriz="9", data_servico=hoje - timedelta(days=10), ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    cand = next(x for x in r.json()["candidatas"] if x["numero_matriz"] == "2")
    assert cand["apta_na_proxima_visita"] is True
    assert cand["apta_hoje"] is False, "hoje ainda está dentro do PEV"


def test_ainda_no_pev_na_data_da_visita_nem_aparece(client):
    """Antes ela vinha na lista com `apta_na_proxima_visita=False`. Agora a
    lista É a lista da visita: quem não estará apta lá não entra."""
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="3", sexo="F", ativo=True, sit_rep="Vaz. atr."))
        s.add(Parto(numero_matriz="3", data_parto=hoje - timedelta(days=5), ordem_parto=1))
        s.add(Servico(numero_matriz="9", data_servico=hoje - timedelta(days=10), ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    assert all(x["numero_matriz"] != "3" for x in r.json()["candidatas"])


def test_diagnostico_negativo_refina_o_motivo(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="4", sexo="F", ativo=True, sit_rep=""))
        s.add(Parto(numero_matriz="4", data_parto=hoje - timedelta(days=100), ordem_parto=1))
        s.add(Servico(numero_matriz="4", data_servico=hoje - timedelta(days=5), ordem_tentativa=1,
                      diagnostico="NEGATIVO", ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    cand = next(x for x in r.json()["candidatas"] if x["numero_matriz"] == "4")
    assert cand["motivo"] == "Diagnóstico negativo"


def test_gestante_pelo_app_sai_mesmo_com_sit_rep_dizendo_vazia(client):
    """O defeito que a migração existe para resolver: o CSV está velho e diz
    'Vaz. apt.', mas o diagnóstico positivo já foi lançado no sistema."""
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="5", sexo="F", ativo=True, sit_rep="Vaz. apt."))
        s.add(Parto(numero_matriz="5", data_parto=hoje - timedelta(days=200), ordem_parto=1))
        s.add(Servico(numero_matriz="5", data_servico=hoje - timedelta(days=40), ordem_tentativa=1,
                      diagnostico="POSITIVO", ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    assert all(x["numero_matriz"] != "5" for x in r.json()["candidatas"])


def test_marcada_a_descartar_sai_da_lista(client):
    """R1 — `a_descartar` tira do programa. `classificar_animal` não consulta
    esse campo; quem faz o corte é `estado_no_dia`."""
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="6", sexo="F", ativo=True, sit_rep="Vaz. apt.", a_descartar=True))
        s.add(Parto(numero_matriz="6", data_parto=hoje - timedelta(days=120), ordem_parto=1))
        s.add(Servico(numero_matriz="9", data_servico=hoje - timedelta(days=10), ordem_tentativa=1, ult_ocorrencia=1))
        s.commit()
    r = c.get("/reproducao/protocolo-iatf/candidatas")
    assert all(x["numero_matriz"] != "6" for x in r.json()["candidatas"])
