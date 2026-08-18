"""
Alerta na Agenda no dia seguinte ao pagamento da PENÚLTIMA etapa de uma
empreitada por etapa — avisa para preparar/fechar a última etapa (ver
EmpreitadaEtapa, routers/agenda.py bloco "empreitada_penultima_etapa").
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import ContaGerencial, Empreitada, EmpreitadaEtapa, Pessoa


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


HOJE = date(2026, 8, 16)
ONTEM = HOJE - timedelta(days=1)


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    yield main.app, engine
    main.app.dependency_overrides.clear()


def _client(app):
    from fazenda.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    return TestClient(app)


def _montar_empreitada(s: Session, n_etapas: int = 3) -> Empreitada:
    pessoa = Pessoa(nome="Carlos Empreiteiro", tipo="Empreiteiro", ativo=True)
    s.add(pessoa)
    s.commit()
    s.refresh(pessoa)
    empreitada = Empreitada(pessoa_id=pessoa.id, descricao="Reforma do curral", valor_total=9000.0, tipo_pagamento="por_etapa")
    s.add(empreitada)
    s.commit()
    s.refresh(empreitada)
    etapas = []
    for i in range(n_etapas):
        numero_lancamento = f"LC-ETAPA-{empreitada.id}-{i}"
        s.add(ContaGerencial(numero_lancamento=numero_lancamento, valor_total=3000.0, tipo="despesa"))
        etapa = EmpreitadaEtapa(
            empreitada_id=empreitada.id, nome=f"Etapa {i + 1}", valor=3000.0, ordem=i,
            concluida=True, numero_lancamento_gerado=numero_lancamento,
        )
        s.add(etapa)
        etapas.append(etapa)
    s.commit()
    for e in etapas:
        s.refresh(e)
    return empreitada, etapas


def _pagar_etapa(s: Session, etapa: EmpreitadaEtapa, data_pagamento: date):
    from sqlmodel import select
    conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == etapa.numero_lancamento_gerado)).first()
    conta.data_pagamento = data_pagamento
    conta.valor_pago = conta.valor_total
    s.add(conta)
    s.commit()


def test_alerta_dispara_no_dia_seguinte_ao_pagamento_da_penultima_etapa(setup):
    app, engine = setup
    with Session(engine) as s:
        empreitada, etapas = _montar_empreitada(s, 3)
        _pagar_etapa(s, etapas[1], ONTEM)  # etapa[1] = penúltima (ordem 0,1,2)

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=5")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert any("Carlos Empreiteiro" in d and "Penúltima etapa" in d for d in descricoes)


def test_pagar_a_primeira_etapa_nao_dispara_alerta(setup):
    app, engine = setup
    with Session(engine) as s:
        empreitada, etapas = _montar_empreitada(s, 3)
        _pagar_etapa(s, etapas[0], ONTEM)  # não é a penúltima

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=5")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("Penúltima etapa" in d for d in descricoes)


def test_pagar_a_ultima_etapa_nao_dispara_alerta(setup):
    app, engine = setup
    with Session(engine) as s:
        empreitada, etapas = _montar_empreitada(s, 3)
        _pagar_etapa(s, etapas[2], ONTEM)  # última etapa

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=5")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("Penúltima etapa" in d for d in descricoes)


def test_pagamento_de_2_dias_atras_nao_dispara_mais(setup):
    """O alerta é só "no dia seguinte" — não persiste depois disso."""
    app, engine = setup
    with Session(engine) as s:
        empreitada, etapas = _montar_empreitada(s, 3)
        _pagar_etapa(s, etapas[1], HOJE - timedelta(days=2))

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=5")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("Penúltima etapa" in d for d in descricoes)


def test_empreitada_com_apenas_2_etapas_a_primeira_e_a_penultima(setup):
    app, engine = setup
    with Session(engine) as s:
        empreitada, etapas = _montar_empreitada(s, 2)
        _pagar_etapa(s, etapas[0], ONTEM)  # com só 2 etapas, a etapa 0 é a penúltima

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=5")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert any("Penúltima etapa" in d for d in descricoes)
