"""`estado_reprodutivo` em GET /animais/ e na ficha — teste de IDA-E-VOLTA (lança no sistema -> o campo aparece na
resposta; o Pydantic/serialização não pode engolir o campo novo). Cobre o caso do bot Hermes: vaca com toque positivo
lançado e `categoria_completa` velha ("vazia em atraso") deve sair como "Gestante".
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Parto, Servico

HOJE = date.today()


@pytest.fixture
def ctx():
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


def _vaca(s, numero, categoria, **kw):
    s.add(Animal(numero=numero, sexo="F", ativo=True, categoria_completa=categoria, categoria_abrev=categoria, **kw))
    s.add(Parto(numero_matriz=numero, data_parto=HOJE - timedelta(days=300), ordem_parto=1))


def _lista(c):
    return {a["numero"]: a for a in c.get("/animais/").json()}


def test_toque_positivo_lancado_aparece_gestante_apesar_do_texto_velho(ctx):
    c, engine = ctx
    with Session(engine) as s:
        _vaca(s, "100", "Vaca vazia em atraso")
        s.add(Servico(numero_matriz="100", data_servico=HOJE - timedelta(days=60)))
        s.commit()
    assert _lista(c)["100"]["estado_reprodutivo"] == "Inseminada"
    r = c.post("/reproducao/diagnostico", json={
        "numero_matriz": "100", "data_diagnostico": HOJE.isoformat(), "resultado": "retoque"})
    assert r.status_code == 200
    animal = _lista(c)["100"]
    assert animal["estado_reprodutivo"] == "Gestante"
    assert animal["estado_reprodutivo_codigo"] == "gestante"
    assert animal["categoria_completa"] == "Vaca vazia em atraso"  # o texto NÃO é reescrito
    assert animal["data_ult_servico_pos"] == (HOJE - timedelta(days=60)).isoformat()
    ficha = c.get("/animais/100/ficha").json()["animal"]
    assert ficha["estado_reprodutivo"] == "Gestante"


def test_reconfirmacao_negativa_tira_data_ult_servico_pos_e_vira_apta(ctx):
    c, engine = ctx
    with Session(engine) as s:
        _vaca(s, "101", "Vaca ges. lac.")
        s.add(Servico(numero_matriz="101", data_servico=HOJE - timedelta(days=70), diagnostico="POSITIVO",
                      data_diagnostico=HOJE - timedelta(days=40), diagnostico_reconfirmacao="NEGATIVO",
                      data_reconfirmacao=HOJE - timedelta(days=2)))
        s.commit()
    animal = _lista(c)["101"]
    assert animal["data_ult_servico_pos"] is None
    assert animal["estado_reprodutivo"] in ("Apta", "Atrasada")


def test_macho_e_semen_ficam_sem_estado(ctx):
    c, engine = ctx
    with Session(engine) as s:
        s.add(Animal(numero="900", sexo="M", ativo=True))
        s.commit()
    r = c.get("/animais/", params={"incluir_machos": True})
    macho = next(a for a in r.json() if a["numero"] == "900")
    assert "estado_reprodutivo" in macho and macho["estado_reprodutivo"] is None


def test_sem_n_mais_um(ctx):
    """O número de consultas não cresce com o número de animais."""
    c, engine = ctx

    proximo = [1000]

    def consultas(qtd_animais: int) -> int:
        with Session(engine) as s:
            for _ in range(qtd_animais):
                n = str(proximo[0])
                proximo[0] += 1
                _vaca(s, n, "Vaca vazia")
                s.add(Servico(numero_matriz=n, data_servico=HOJE - timedelta(days=30)))
            s.commit()
        contador = []
        def _conta(*a, **k):
            contador.append(1)
        event.listen(engine, "before_cursor_execute", _conta)
        try:
            assert c.get("/animais/").status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _conta)
        return len(contador)

    pouco = consultas(3)
    muito = consultas(40)
    assert muito <= pouco + 2, (pouco, muito)
