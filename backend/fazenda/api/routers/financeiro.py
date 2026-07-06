"""
Router financeiro — DRE, fluxo de caixa e KPIs financeiros.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import ContaGerencial

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


@router.get("/dre")
def dre(
    data_inicio: date = Query(..., description="Data inicial (competência)"),
    data_fim: date = Query(..., description="Data final (competência)"),
    centro_custo: Optional[str] = Query(None),
    regime: str = Query("competencia", description="'competencia' ou 'caixa'"),
    session: Session = Depends(get_session),
) -> dict:
    """
    Retorna DRE (Demonstrativo de Resultado) por regime de competência ou caixa.
    """
    campo_data = "data_competencia" if regime == "competencia" else "data_pagamento"

    contas = session.exec(select(ContaGerencial)).all()

    filtradas = []
    for c in contas:
        data_ref = c.data_competencia if regime == "competencia" else c.data_pagamento
        if data_ref and data_inicio <= data_ref <= data_fim:
            if centro_custo is None or c.centro_custo == centro_custo:
                filtradas.append(c)

    receitas = sum(c.valor_total or 0 for c in filtradas if c.tipo == "receita")
    despesas = sum(c.valor_total or 0 for c in filtradas if c.tipo == "despesa")
    resultado = receitas - despesas

    # Agrupa por código de conta
    por_conta: dict[str, dict] = {}
    for c in filtradas:
        codigo = c.codigo_conta or "Sem classificação"
        nivel1 = codigo.split(".")[0] if "." in codigo else codigo
        if nivel1 not in por_conta:
            por_conta[nivel1] = {"descricao": c.descricao or "", "receitas": 0.0, "despesas": 0.0}
        if c.tipo == "receita":
            por_conta[nivel1]["receitas"] += c.valor_total or 0
        else:
            por_conta[nivel1]["despesas"] += c.valor_total or 0

    return {
        "periodo": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
        "regime": regime,
        "centro_custo": centro_custo,
        "receitas_total": round(receitas, 2),
        "despesas_total": round(despesas, 2),
        "resultado": round(resultado, 2),
        "por_conta": por_conta,
    }


@router.get("/lancamentos")
def listar_lancamentos(session: Session = Depends(get_session)) -> dict:
    """
    Movimentações achatadas para o dashboard financeiro interativo.
    O front filtra por regime (competência/caixa), ano e centro de custo.
    """
    registros = []
    for c in session.exec(select(ContaGerencial)).all():
        dc = c.data_competencia
        dp = c.data_pagamento
        registros.append({
            "tipo": c.tipo,
            "valor": c.valor_total or 0.0,
            "valor_pago": c.valor_pago,
            "centro_custo": c.centro_custo or "(sem centro)",
            "codigo_conta": (c.codigo_conta or "").split(".")[0] or "(sem conta)",
            "conta_completa": c.codigo_conta or "",
            "descricao": c.descricao or "",
            "fornecedor": c.fornecedor_cliente or "",
            "data_competencia": dc.isoformat() if dc else None,
            "data_pagamento": dp.isoformat() if dp else None,
            "data_vencimento": c.data_vencimento.isoformat() if c.data_vencimento else None,
            "mes_competencia": f"{dc.year}-{dc.month:02d}" if dc else None,
            "ano_competencia": dc.year if dc else None,
            "mes_caixa": f"{dp.year}-{dp.month:02d}" if dp else None,
            "ano_caixa": dp.year if dp else None,
        })
    return {"lancamentos": registros, "total": len(registros)}


@router.get("/contas-a-pagar")
def contas_a_pagar(
    dias: int = Query(10, description="Janela em dias"),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Retorna contas com vencimento nos próximos N dias (não quitadas)."""
    hoje = date.today()
    limite = hoje + __import__("datetime").timedelta(days=dias)

    contas = session.exec(select(ContaGerencial)).all()
    resultado = []
    for c in contas:
        if (
            c.data_vencimento
            and hoje <= c.data_vencimento <= limite
            and (c.valor_pago or 0) < (c.valor_total or 0)
            and c.tipo == "despesa"
        ):
            resultado.append(c.model_dump())

    return sorted(resultado, key=lambda x: x["data_vencimento"])
