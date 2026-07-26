"""
Custo por hectare e por tonelada de uma Safra — Opção A do plano de custo
agrícola (indicador Financeiro > Relatórios; arquivo próprio para não mexer
em financeiro.py — mesmo espírito de relatorio_custo_hectare.py e
relatorio_custo_producao.py, reaproveitando o prefixo /financeiro).

Soma as despesas do Financeiro (ContaGerencial) lançadas no centro de custo e
no período (competência) da safra, divide pelo hectare/tonelada cadastrados
nela e quebra o total por categoria — nível 1 do código da conta gerencial,
mesmo agrupamento usado no DRE (GET /financeiro/dre).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import ContaGerencial, Safra
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.custo_safra import calcular_custo_safra

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


@router.get("/custo-safra")
def custo_por_safra(
    safra_id: int = Query(...),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    safra = session.get(Safra, safra_id)
    if not safra:
        raise HTTPException(status_code=404, detail="Safra não encontrada")

    query_contas = select(ContaGerencial)
    if fazenda_id is not None:
        query_contas = query_contas.where(ContaGerencial.fazenda_id == fazenda_id)
    contas = session.exec(query_contas).all()
    filtradas = [
        c for c in contas
        if c.tipo == "despesa" and c.centro_custo == safra.centro_custo
        and c.data_competencia and safra.data_inicio <= c.data_competencia <= safra.data_fim
    ]
    despesas_total = sum(c.valor_total or 0 for c in filtradas)

    # Mesmo agrupamento do DRE: nível 1 do código da conta, rótulo pela
    # primeira descrição encontrada para aquele nível.
    por_categoria: dict[str, dict] = {}
    for c in filtradas:
        codigo = c.codigo_conta or "Sem classificação"
        nivel1 = codigo.split(".")[0] if "." in codigo else codigo
        if nivel1 not in por_categoria:
            por_categoria[nivel1] = {"descricao": c.descricao or "", "valor": 0.0}
        por_categoria[nivel1]["valor"] += c.valor_total or 0

    lista_categorias = [
        {"codigo": k, "descricao": v["descricao"], "valor": round(v["valor"], 2)}
        for k, v in sorted(por_categoria.items(), key=lambda kv: -kv[1]["valor"])
    ]

    return {
        "safra": safra.model_dump(),
        "por_categoria": lista_categorias,
        **calcular_custo_safra(despesas_total, safra.hectares, safra.toneladas_produzidas),
    }
