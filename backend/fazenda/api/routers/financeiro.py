"""
Router financeiro — DRE, fluxo de caixa, KPIs e lançamentos financeiros
(contas a pagar/a receber, com parcelamento, conta bancária e importação de XML).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import ContaGerencial
from fazenda.rules.nfe_xml import parse_nfe_xml

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

# As duas contas correntes da fazenda no Banco do Brasil.
CONTAS_BANCARIAS = [
    "Banco do Brasil · Agência 3775-3 · Conta corrente 3.615-3",
    "Banco do Brasil · Agência 4057-6 · Conta corrente 3.615-3",
]
TIPOS_DOCUMENTO = ["Nota fiscal", "Recibo", "Folha de pagamento", "Fatura", "Contrato"]


class ParcelaIn(BaseModel):
    data_vencimento: date
    valor: float


class LancamentoIn(BaseModel):
    tipo: str  # "receita" | "despesa"
    codigo_conta: Optional[str] = None
    descricao: Optional[str] = None
    centro_custo: Optional[str] = None
    fornecedor_cliente: Optional[str] = None
    responsavel: Optional[str] = None
    tipo_documento: Optional[str] = None
    numero_documento: Optional[str] = None
    data_emissao: Optional[date] = None
    data_competencia: Optional[date] = None
    data_prevista_entrada: Optional[date] = None
    data_pedido: Optional[date] = None
    entregue: Optional[bool] = None
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: float
    parcelas: list[ParcelaIn] = []
    # Preenchidos só quando o lançamento já nasce pago/recebido (sem parcelamento).
    data_pagamento: Optional[date] = None
    valor_pago: Optional[float] = None
    conta_bancaria: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None


class PagamentoIn(BaseModel):
    data_pagamento: date
    valor_pago: float
    conta_bancaria: Optional[str] = None
    numero_documento_pagamento: Optional[str] = None


class XmlIn(BaseModel):
    xml: str


def _proximo_numero_lancamento(session: Session, ano: int) -> str:
    prefixo = f"LC-{ano}-"
    existentes = session.exec(
        select(ContaGerencial.numero_lancamento).where(ContaGerencial.numero_lancamento.like(f"{prefixo}%"))
    ).all()
    maior = 0
    for n in existentes:
        if n and n.startswith(prefixo):
            try:
                maior = max(maior, int(n[len(prefixo):]))
            except ValueError:
                continue
    return f"{prefixo}{maior + 1:05d}"


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
            "id": c.id,
            "numero_lancamento": c.numero_lancamento,
            "tipo": c.tipo,
            "valor": c.valor_total or 0.0,
            "valor_pago": c.valor_pago,
            "desconto_acrescimo": c.desconto_acrescimo,
            "centro_custo": c.centro_custo or "(sem centro)",
            "codigo_conta": (c.codigo_conta or "").split(".")[0] or "(sem conta)",
            "conta_completa": c.codigo_conta or "",
            "descricao": c.descricao or "",
            "fornecedor": c.fornecedor_cliente or "",
            "responsavel": c.responsavel,
            "tipo_documento": c.tipo_documento,
            "numero_documento": c.numero_nota,
            "numero_documento_pagamento": c.numero_documento_pagamento,
            "conta_bancaria": c.conta_bancaria,
            "quantidade": c.quantidade,
            "valor_unitario": c.valor_unitario,
            "entregue": c.entregue,
            "parcela_num": c.parcela_num,
            "parcela_total": c.parcela_total,
            "origem": c.origem,
            "data_competencia": dc.isoformat() if dc else None,
            "data_pagamento": dp.isoformat() if dp else None,
            "data_vencimento": c.data_vencimento.isoformat() if c.data_vencimento else None,
            "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None,
            "data_prevista_entrada": c.data_prevista_entrada.isoformat() if c.data_prevista_entrada else None,
            "data_pedido": c.data_pedido.isoformat() if c.data_pedido else None,
            "mes_competencia": f"{dc.year}-{dc.month:02d}" if dc else None,
            "ano_competencia": dc.year if dc else None,
            "mes_caixa": f"{dp.year}-{dp.month:02d}" if dp else None,
            "ano_caixa": dp.year if dp else None,
        })
    return {"lancamentos": registros, "total": len(registros)}


@router.get("/opcoes")
def opcoes(session: Session = Depends(get_session)) -> dict:
    """Listas para os seletores do lançamento — derivadas dos dados já importados."""
    contas = session.exec(select(ContaGerencial)).all()
    contas_gerenciais = sorted({
        (c.codigo_conta, c.descricao) for c in contas if c.codigo_conta or c.descricao
    }, key=lambda x: (x[0] or "", x[1] or ""))
    centros_custo = sorted({c.centro_custo for c in contas if c.centro_custo})
    fornecedores = sorted({c.fornecedor_cliente for c in contas if c.fornecedor_cliente})
    return {
        "contas_gerenciais": [{"codigo": c[0], "descricao": c[1]} for c in contas_gerenciais],
        "centros_custo": centros_custo,
        "fornecedores": fornecedores,
        "contas_bancarias": CONTAS_BANCARIAS,
        "tipos_documento": TIPOS_DOCUMENTO,
    }


@router.post("/lancamentos", status_code=201)
def criar_lancamento(dados: LancamentoIn, session: Session = Depends(get_session)) -> dict:
    """
    Cria um lançamento financeiro. Se houver parcelamento, gera uma linha por
    parcela, todas com o mesmo número de referência (numero_lancamento).
    Sem data de pagamento, o lançamento nasce em aberto (contas a pagar/receber).
    """
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'receita' ou 'despesa'")

    ano = (dados.data_emissao or dados.data_competencia or date.today()).year
    numero_lancamento = _proximo_numero_lancamento(session, ano)

    campos_comuns = dict(
        numero_lancamento=numero_lancamento,
        codigo_conta=dados.codigo_conta,
        descricao=dados.descricao,
        centro_custo=dados.centro_custo,
        fornecedor_cliente=dados.fornecedor_cliente,
        responsavel=dados.responsavel,
        tipo_documento=dados.tipo_documento,
        numero_nota=dados.numero_documento,
        data_emissao=dados.data_emissao,
        data_competencia=dados.data_competencia or dados.data_emissao,
        data_prevista_entrada=dados.data_prevista_entrada,
        data_pedido=dados.data_pedido,
        entregue=dados.entregue,
        quantidade=dados.quantidade,
        valor_unitario=dados.valor_unitario,
        tipo=dados.tipo,
        origem="manual",
    )

    criados: list[ContaGerencial] = []
    if dados.parcelas:
        total_parcelas = len(dados.parcelas)
        for i, p in enumerate(dados.parcelas, start=1):
            criados.append(ContaGerencial(
                **campos_comuns,
                data_vencimento=p.data_vencimento,
                valor_total=p.valor,
                parcela_num=i,
                parcela_total=total_parcelas,
            ))
    else:
        registro = ContaGerencial(
            **campos_comuns,
            data_vencimento=dados.data_prevista_entrada,
            valor_total=dados.valor_total,
            parcela_num=1,
            parcela_total=1,
        )
        if dados.data_pagamento:
            registro.data_pagamento = dados.data_pagamento
            registro.valor_pago = dados.valor_pago
            registro.conta_bancaria = dados.conta_bancaria
            registro.numero_documento_pagamento = dados.numero_documento_pagamento
            registro.desconto_acrescimo = round((dados.valor_pago or 0) - dados.valor_total, 2)
        criados.append(registro)

    for c in criados:
        session.add(c)
    session.commit()
    for c in criados:
        session.refresh(c)

    return {"numero_lancamento": numero_lancamento, "ids": [c.id for c in criados]}


@router.put("/lancamentos/{lancamento_id}/pagar")
def pagar_lancamento(lancamento_id: int, dados: PagamentoIn, session: Session = Depends(get_session)) -> dict:
    """Dá baixa (marca como pago/recebido) numa conta a pagar/a receber."""
    registro = session.get(ContaGerencial, lancamento_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")

    registro.data_pagamento = dados.data_pagamento
    registro.valor_pago = dados.valor_pago
    registro.conta_bancaria = dados.conta_bancaria
    registro.numero_documento_pagamento = dados.numero_documento_pagamento
    registro.desconto_acrescimo = round(dados.valor_pago - (registro.valor_total or 0), 2)
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.post("/importar-xml")
def importar_xml(dados: XmlIn) -> dict:
    """Extrai os campos de um XML de NF-e para pré-preencher o lançamento."""
    try:
        return parse_nfe_xml(dados.xml)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Não foi possível ler o XML: {e}")


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
