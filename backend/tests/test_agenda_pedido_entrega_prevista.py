"""
Alerta na Agenda "já foi entregue?" para Pedido aberto/parcialmente atendido
com `data_prevista` — persistente (sem piso nem teto de data), mesmo racional
do Pré-parto/Secagem: fica visível antes E depois da data prevista, e só some
quando o pedido deixa de estar aberto/parcialmente atendido (entrega marcada
ou pedido cancelado), nunca pela data ter passado (ver AgendaEngine bloco
"5c-bis").
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import Pedido


class _FakeAdmin:
    id = 1
    papel = "admin"
    permissoes = None
    ativo = True
    username = "admin_teste"


HOJE = date(2026, 8, 16)


def _pedido(**overrides) -> Pedido:
    dados = dict(numero_pedido="PED-2026-00001", tipo="compra", status="aberto", data_pedido=HOJE)
    dados.update(overrides)
    return Pedido(**dados)


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


def test_pedido_aberto_com_data_prevista_passada_dispara_alerta_atrasado(setup):
    """Data prevista já passou e o pedido segue aberto — o alerta continua
    aparecendo (sem piso de data), diferente do idioma 'expira' do bloco 5c."""
    app, engine = setup
    with Session(engine) as s:
        s.add(_pedido(data_prevista=HOJE - timedelta(days=10)))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert any("PED-2026-00001" in d and "entregue" in d for d in descricoes)


def test_pedido_aberto_com_data_prevista_futura_ja_dispara_alerta(setup):
    """Não é só 'vencido': o lembrete já aparece antes da data prevista chegar
    (heads-up), sem esperar nenhuma janela de antecedência."""
    app, engine = setup
    with Session(engine) as s:
        s.add(_pedido(numero_pedido="PED-2026-00002", data_prevista=HOJE + timedelta(days=45)))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert any("PED-2026-00002" in d for d in descricoes)


def test_pedido_sem_data_prevista_nao_dispara_alerta(setup):
    app, engine = setup
    with Session(engine) as s:
        s.add(_pedido(data_prevista=None))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("PED-2026-00001" in d for d in descricoes)


def test_pedido_atendido_nao_dispara_alerta_mesmo_com_data_prevista_passada(setup):
    """Entrega já resolvida (status calculado a partir de quantidade_entregue,
    ver pedido_status.py) — o alerta desaparece, mesmo com a data no passado."""
    app, engine = setup
    with Session(engine) as s:
        s.add(_pedido(status="atendido", data_prevista=HOJE - timedelta(days=10)))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("PED-2026-00001" in d for d in descricoes)


def test_pedido_cancelado_nao_dispara_alerta_mesmo_com_data_prevista_passada(setup):
    app, engine = setup
    with Session(engine) as s:
        s.add(_pedido(status="cancelado", data_prevista=HOJE - timedelta(days=10)))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("PED-2026-00001" in d for d in descricoes)


def test_pedido_parcialmente_atendido_com_data_prevista_passada_dispara_alerta(setup):
    """Ainda não terminou de chegar — segue "aberto" pro efeito deste alerta
    (status "parcialmente_atendido" também entra no filtro)."""
    app, engine = setup
    with Session(engine) as s:
        s.add(_pedido(status="parcialmente_atendido", data_prevista=HOJE - timedelta(days=3)))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert any("PED-2026-00001" in d for d in descricoes)
