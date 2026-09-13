"""
Alerta na Agenda quando um orçamento/ordem de serviço anexado a um Pedido
está com a validade vencendo — dispara 2 dias antes, enquanto o pedido
segue "aberto"/"parcialmente_atendido" (ver PedidoAnexo, AgendaEngine
bloco "5c").
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import Pedido, PedidoAnexo


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


def test_alerta_dispara_2_dias_antes_do_vencimento(setup):
    app, engine = setup
    with Session(engine) as s:
        pedido = _pedido()
        s.add(pedido)
        s.commit()
        s.refresh(pedido)
        s.add(PedidoAnexo(
            pedido_id=pedido.id, nome_arquivo="orcamento.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria="Orçamento", data_validade=HOJE + timedelta(days=2),
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert any("PED-2026-00001" in d and "vence em" in d for d in descricoes)


def test_sem_data_validade_nao_dispara_alerta(setup):
    app, engine = setup
    with Session(engine) as s:
        pedido = _pedido()
        s.add(pedido)
        s.commit()
        s.refresh(pedido)
        s.add(PedidoAnexo(
            pedido_id=pedido.id, nome_arquivo="orcamento.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria="Orçamento", data_validade=None,
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("PED-2026-00001" in d for d in descricoes)


def test_pedido_atendido_nao_dispara_alerta(setup):
    app, engine = setup
    with Session(engine) as s:
        pedido = _pedido(status="atendido")
        s.add(pedido)
        s.commit()
        s.refresh(pedido)
        s.add(PedidoAnexo(
            pedido_id=pedido.id, nome_arquivo="orcamento.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria="Orçamento", data_validade=HOJE + timedelta(days=2),
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("PED-2026-00001" in d for d in descricoes)


def test_pedido_cancelado_nao_dispara_alerta(setup):
    app, engine = setup
    with Session(engine) as s:
        pedido = _pedido(status="cancelado")
        s.add(pedido)
        s.commit()
        s.refresh(pedido)
        s.add(PedidoAnexo(
            pedido_id=pedido.id, nome_arquivo="os.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria="Ordem de serviço", data_validade=HOJE + timedelta(days=2),
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("PED-2026-00001" in d for d in descricoes)


def test_fora_da_janela_de_2_dias_nao_dispara_ainda(setup):
    """Vencimento daqui a 30 dias — o alerta (vencimento-2) só entra na janela quando `dias` for grande o suficiente."""
    app, engine = setup
    with Session(engine) as s:
        pedido = _pedido()
        s.add(pedido)
        s.commit()
        s.refresh(pedido)
        s.add(PedidoAnexo(
            pedido_id=pedido.id, nome_arquivo="orcamento.pdf", mime_type="application/pdf",
            tamanho_bytes=100, categoria="Orçamento", data_validade=HOJE + timedelta(days=30),
        ))
        s.commit()

    c = _client(app)
    r = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=10")
    assert r.status_code == 200
    descricoes = [e["descricao"] for e in r.json()["eventos"]]
    assert not any("PED-2026-00001" in d for d in descricoes)

    r2 = c.get(f"/agenda/?data={HOJE.isoformat()}&dias=30")
    assert r2.status_code == 200
    descricoes2 = [e["descricao"] for e in r2.json()["eventos"]]
    assert any("PED-2026-00001" in d for d in descricoes2)
