"""
Parto/nascimento — SEXO DA CRIA OBRIGATÓRIO (decisão do dono): cria com número e
sem sexo é recusada com 422 nos DOIS endpoints que recebem `CriaIn`
(POST /reproducao/parto e POST /reproducao/encerramento-gestacao, este último
usado também pelo app de campo) e o robô do Telegram não assume mais "F".
"""
from __future__ import annotations

import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Parto

HOJE = date.today()


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def client(engine):
    lock = threading.Lock()

    def _get_session_override():
        with lock, Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: None
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: None

    with TestClient(main.app) as c:
        c.engine = engine
        yield c

    main.app.dependency_overrides.clear()


def _mae(engine, numero="500"):
    with Session(engine) as s:
        s.add(Animal(numero=numero, sexo="F", ativo=True))
        s.commit()


def _nada_gravado(engine, cria_numero):
    with Session(engine) as s:
        assert s.exec(select(Parto)).first() is None
        assert s.exec(select(Animal).where(Animal.numero == cria_numero)).first() is None


@pytest.mark.parametrize("sexo", ["", "   ", "X", "Fêmea"])
def test_parto_com_numero_e_sem_sexo_valido_da_422(client, engine, sexo):
    _mae(engine)
    r = client.post("/reproducao/parto", json={
        "numero_matriz": "500", "data_parto": HOJE.isoformat(),
        "crias": [{"numero": "9001", "sexo": sexo, "nasceu_viva": True}],
    })
    assert r.status_code == 422
    assert "sexo" in r.text.lower()
    _nada_gravado(engine, "9001")


def test_parto_sem_o_campo_sexo_da_422(client, engine):
    _mae(engine)
    r = client.post("/reproducao/parto", json={
        "numero_matriz": "500", "data_parto": HOJE.isoformat(), "crias": [{"numero": "9001"}],
    })
    assert r.status_code == 422
    _nada_gravado(engine, "9001")


def test_encerramento_gestacao_com_numero_e_sem_sexo_da_422(client, engine):
    """Mesmo endpoint do app de campo (/app)."""
    _mae(engine)
    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "500", "data": HOJE.isoformat(), "tipo": "parto",
        "crias": [{"numero": "9002", "sexo": "", "nasceu_viva": True}],
    })
    assert r.status_code == 422
    _nada_gravado(engine, "9002")


def test_segunda_cria_gemelar_sem_sexo_da_422_e_nao_grava_a_primeira(client, engine):
    _mae(engine)
    r = client.post("/reproducao/parto", json={
        "numero_matriz": "500", "data_parto": HOJE.isoformat(), "gemelar": True,
        "crias": [{"numero": "9003", "sexo": "F"}, {"numero": "9004", "sexo": ""}],
    })
    assert r.status_code == 422
    _nada_gravado(engine, "9003")


def test_parto_com_sexo_grava_e_normaliza_para_maiuscula(client, engine):
    _mae(engine)
    r = client.post("/reproducao/parto", json={
        "numero_matriz": "500", "data_parto": HOJE.isoformat(),
        "crias": [{"numero": "9005", "sexo": "m", "nasceu_viva": True}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["crias_criadas"] == ["9005"]
    with Session(engine) as s:
        cria = s.exec(select(Animal).where(Animal.numero == "9005")).one()
        assert cria.sexo == "M" and cria.categoria_abrev == "Bezerro"
        assert s.exec(select(Parto)).one().sexo_cria_1 == "M"


def test_cria_sem_numero_continua_sem_exigir_sexo(client, engine):
    """Baixa automática (natimorto sem ficha): não cadastra animal, o sexo pode vir vazio."""
    _mae(engine)
    r = client.post("/reproducao/parto", json={
        "numero_matriz": "500", "data_parto": HOJE.isoformat(), "tipo_parto": "Natimorto",
        "crias": [{"numero": "", "sexo": "", "nasceu_viva": False}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["crias_criadas"] == []


def test_natimorto_com_numero_baixado_ainda_exige_sexo(client, engine):
    """Relatório de % machos/fêmeas: natimorto também precisa do sexo."""
    _mae(engine)
    r = client.post("/reproducao/parto", json={
        "numero_matriz": "500", "data_parto": HOJE.isoformat(), "tipo_parto": "Natimorto",
        "crias": [{"numero": "9006", "sexo": "", "nasceu_viva": False}],
    })
    assert r.status_code == 422


def test_aborto_sem_crias_nao_e_afetado(client, engine):
    _mae(engine)
    r = client.post("/reproducao/encerramento-gestacao", json={
        "numero_matriz": "500", "data": HOJE.isoformat(), "tipo": "aborto", "abrir_lactacao": False, "motivo": "aborto",
    })
    assert r.status_code == 200, r.text


def test_telegram_nao_assume_femea_quando_falta_o_sexo(engine):
    """O executor do fluxo 'parto' (aprovação do lançamento do Telegram) não usa mais o default 'F'."""
    from fazenda.rules import telegram_fluxos as fx

    campos = {c["chave"]: c for c in fx.FLUXOS["parto"]["campos"]}
    sexo = campos["cria_sexo"]
    assert sexo["obrigatorio"] is True
    assert sexo["quando"]({"cria_numero": "9007"}) is True
    assert sexo["quando"]({}) is False  # "pular" no número da cria => nem pergunta o sexo

    _mae(engine)
    with Session(engine) as s:
        class _U:
            id = 1
            papel = "admin"
        with pytest.raises(Exception) as exc:
            fx.criar_registro("parto", {"numero_matriz": "500", "data_parto": HOJE.isoformat(), "cria_numero": "9007"},
                              s, user=_U(), fazenda_id=1)
        assert "sexo" in str(exc.value).lower()
        assert s.exec(select(Animal).where(Animal.numero == "9007")).first() is None
