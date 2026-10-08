"""Financeiro > Relatórios > Réguas de referência: faixas de mercado com fonte e validade.

Somente leitura e igual para todas as fazendas (sem dado de cliente). Os dados vêm de
`seed_data/reguas_referencia.json`, mantido pela rotina mensal (ver
docs/agents/reguas-referencia-mensal.md).
"""
from fastapi import APIRouter

from fazenda.rules import reguas_referencia

router = APIRouter(prefix="/financeiro/reguas-referencia", tags=["financeiro"])


@router.get("")
def reguas_de_referencia():
    return reguas_referencia.publico()
