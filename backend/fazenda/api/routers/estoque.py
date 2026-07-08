"""
Router de estoque — inventário completo de insumos e lançamento de
entradas/saídas (dá baixa ou soma direto em Estoque.quantidade).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Estoque, MovimentoEstoque

router = APIRouter(prefix="/estoque", tags=["estoque"])

MOVIMENTOS_ENTRADA = ["Entrada de ajuste", "Entrada de cortesia"]
MOVIMENTOS_SAIDA = ["Aplicação", "Saída de ajuste", "Doação"]
MOVIMENTOS_VALIDOS = set(MOVIMENTOS_ENTRADA + MOVIMENTOS_SAIDA)


@router.get("/")
def listar_estoque(session: Session = Depends(get_session)) -> dict:
    """Todos os itens de estoque para o dashboard interativo (filtra no cliente)."""
    itens = [e.model_dump() for e in session.exec(select(Estoque)).all()]
    return {"itens": itens, "total": len(itens)}


@router.get("/movimentos")
def listar_movimentos(session: Session = Depends(get_session)) -> dict:
    """Histórico de entradas/saídas lançadas manualmente."""
    movs = session.exec(select(MovimentoEstoque).order_by(MovimentoEstoque.data_movimento.desc())).all()
    return {"movimentos": [m.model_dump() for m in movs], "total": len(movs)}


class MovimentoIn(BaseModel):
    nome: str
    movimento: str
    quantidade: float
    unidade: str | None = None
    data_movimento: date
    observacao: str | None = None


@router.post("/movimentar")
def movimentar_estoque(dados: MovimentoIn, session: Session = Depends(get_session)) -> dict:
    if dados.movimento not in MOVIMENTOS_VALIDOS:
        raise HTTPException(status_code=400, detail="Tipo de movimento inválido")
    if dados.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero")

    item = session.exec(select(Estoque).where(Estoque.nome == dados.nome)).first()
    if not item:
        raise HTTPException(status_code=404, detail=f'Item de estoque "{dados.nome}" não encontrado')

    baixa = dados.movimento in MOVIMENTOS_SAIDA
    item.quantidade = (item.quantidade or 0) + (-dados.quantidade if baixa else dados.quantidade)
    if item.estoque_minimo is not None:
        item.abaixo_minimo = item.quantidade < item.estoque_minimo
    item.atualizado_em = datetime.utcnow()
    session.add(item)

    session.add(MovimentoEstoque(
        nome_item=dados.nome,
        movimento=dados.movimento,
        quantidade=dados.quantidade,
        unidade=dados.unidade or item.unidade,
        data_movimento=dados.data_movimento,
        observacao=dados.observacao,
    ))
    session.commit()
    session.refresh(item)
    return item.model_dump()
