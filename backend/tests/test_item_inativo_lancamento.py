"""Item de estoque INATIVO não pode ser usado em lançamento novo (compra,
baixa); consultas/estornos seguem enxergando-o. Pedido do dono (03/10/2026)."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Estoque
from fazenda.rules import estoque_baixa


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _item(session, nome, ativo):
    e = Estoque(nome=nome, quantidade=10, unidade="ml", ativo=ativo)
    session.add(e); session.commit(); session.refresh(e)
    return e


def test_baixar_item_inativo_da_409(session):
    item = _item(session, "Banamine", False)
    with pytest.raises(HTTPException) as exc:
        estoque_baixa.baixar(
            session, item=item, quantidade=1, unidade="ml", data=date.today(), fazenda_id=None, observacao="x",
        )
    assert exc.value.status_code == 409
    assert "inativo" in exc.value.detail and "Configurações" in exc.value.detail


def test_baixar_item_ativo_funciona(session):
    item = _item(session, "Ocitocina", True)
    estoque_baixa.baixar(
        session, item=item, quantidade=2, unidade="ml", data=date.today(), fazenda_id=None, observacao="x",
    )
    session.refresh(item)
    assert item.quantidade == 8


def test_devolver_item_inativo_continua_permitido(session):
    """Estorno de lançamento antigo não pode ser bloqueado."""
    item = _item(session, "Antigo", False)
    estoque_baixa.devolver(
        session, item=item, quantidade=2, unidade="ml", data=date.today(), fazenda_id=None, observacao="estorno",
    )
    session.refresh(item)
    assert item.quantidade == 12


def test_opcoes_medicamento_nao_oferece_inativo(session):
    _item(session, "Inativo X", False)
    ativo = _item(session, "Ativo X", True)
    _, opcoes = estoque_baixa.opcoes_medicamento(session, fazenda_id=None, produto="Ativo X")
    assert [o["nome"] for o in opcoes] == ["Ativo X"]
    _, opcoes = estoque_baixa.opcoes_medicamento(session, fazenda_id=None, produto="Inativo X")
    assert opcoes == []
