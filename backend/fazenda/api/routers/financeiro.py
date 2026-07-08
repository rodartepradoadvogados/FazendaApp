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
from fazenda.models import CentroCusto, ContaCorrente, ContaGerencial, LancamentoItem, Patrimonio, PlanoContaGerencial
from fazenda.rules.nfe_xml import parse_nfe_xml

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

TIPOS_DOCUMENTO = ["Nota fiscal", "Recibo", "Folha de pagamento", "Fatura", "Contrato"]

# Seed inicial — as duas contas correntes da fazenda no Banco do Brasil (antes
# uma lista fixa em Python; agora cadastráveis em Configurações > Parâmetros
# financeiros). Ver seed_parametros_financeiros, chamada uma vez no startup.
SEED_CONTAS_CORRENTES = [
    {"banco": "Banco do Brasil", "agencia": "3775-3", "numero_conta": "3.615-3"},
    {"banco": "Banco do Brasil", "agencia": "4057-6", "numero_conta": "3.615-3"},
]


def rotulo_conta_corrente(c: ContaCorrente) -> str:
    return f"{c.banco} · Agência {c.agencia} · Conta corrente {c.numero_conta}"


def seed_parametros_financeiros(session: Session) -> None:
    """Cria as contas correntes padrão se a tabela ainda estiver vazia (idempotente)."""
    if not session.exec(select(ContaCorrente)).first():
        for dados in SEED_CONTAS_CORRENTES:
            session.add(ContaCorrente(**dados))
        session.commit()


class ParcelaIn(BaseModel):
    data_vencimento: date
    valor: float


class ItemIn(BaseModel):
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    produto: str
    descricao: Optional[str] = None
    quantidade: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: float


class LancamentoIn(BaseModel):
    tipo: str  # "receita" | "despesa"
    itens: list[ItemIn]  # um ou mais produtos/serviços da mesma nota
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
    desconto: float = 0
    acrescimo: float = 0
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
    itens_por_lancamento: dict[str, list[dict]] = {}
    for it in session.exec(select(LancamentoItem)).all():
        itens_por_lancamento.setdefault(it.numero_lancamento, []).append({
            "id": it.id,
            "codigo_conta_gerencial": it.codigo_conta_gerencial,
            "nome_conta_gerencial": it.nome_conta_gerencial,
            "produto": it.produto,
            "descricao": it.descricao,
            "quantidade": it.quantidade,
            "valor_unitario": it.valor_unitario,
            "valor_total": it.valor_total,
        })

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
            "desconto_nota": c.desconto_nota,
            "acrescimo_nota": c.acrescimo_nota,
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
            "itens": itens_por_lancamento.get(c.numero_lancamento or "", []),
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


@router.get("/itens-por-conta")
def itens_por_conta(
    data_inicio: date = Query(...),
    data_fim: date = Query(...),
    session: Session = Depends(get_session),
) -> list[dict]:
    """
    Produtos/serviços lançados no período (por competência), um por linha —
    usado no DRE para o detalhamento correto por conta gerencial quando uma
    nota tem vários produtos com contas diferentes.
    """
    itens = session.exec(select(LancamentoItem)).all()
    return [
        {
            "numero_lancamento": it.numero_lancamento,
            "tipo": it.tipo,
            "codigo_conta_gerencial": it.codigo_conta_gerencial,
            "nome_conta_gerencial": it.nome_conta_gerencial,
            "produto": it.produto,
            "valor_total": it.valor_total,
            "data_competencia": it.data_competencia.isoformat() if it.data_competencia else None,
        }
        for it in itens
        if it.data_competencia and data_inicio <= it.data_competencia <= data_fim
    ]


@router.get("/opcoes")
def opcoes(session: Session = Depends(get_session)) -> dict:
    """Listas para os seletores do lançamento — plano de contas real + dados já importados."""
    plano = session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.ativa == True)).all()
    contas_gerenciais = sorted(
        [{"codigo": c.codigo, "nome": c.nome} for c in plano],
        key=lambda x: x["codigo"],
    )
    contas = session.exec(select(ContaGerencial)).all()
    # União com os valores já lançados como texto livre (antes do cadastro
    # formal existir) — nada que já foi usado deixa de aparecer no filtro.
    centros_cadastrados = {c.nome for c in session.exec(select(CentroCusto).where(CentroCusto.ativo == True)).all()}
    centros_custo = sorted(centros_cadastrados | {c.centro_custo for c in contas if c.centro_custo})
    fornecedores = sorted({c.fornecedor_cliente for c in contas if c.fornecedor_cliente})
    produtos = sorted({it.produto for it in session.exec(select(LancamentoItem)).all() if it.produto})
    contas_correntes = session.exec(select(ContaCorrente).where(ContaCorrente.ativo == True)).all()
    return {
        "contas_gerenciais": contas_gerenciais,
        "centros_custo": centros_custo,
        "fornecedores": fornecedores,
        "produtos": produtos,
        "contas_bancarias": [rotulo_conta_corrente(c) for c in contas_correntes],
        "tipos_documento": TIPOS_DOCUMENTO,
    }


@router.get("/plano-contas")
def plano_contas(session: Session = Depends(get_session)) -> list[dict]:
    """
    Plano de contas gerenciais COMPLETO (inclui os códigos de grupo/cabeçalho,
    que vêm com Ativa=Não e não aparecem em /opcoes — aqui servem só para dar
    nome à hierarquia nos relatórios, não para lançar diretamente neles).
    """
    plano = session.exec(select(PlanoContaGerencial)).all()
    return sorted(
        [
            {
                "id": c.id, "codigo": c.codigo, "nome": c.nome, "ativa": c.ativa,
                "nivel": c.codigo.count(".") + 1,
                "fluxo": c.fluxo, "tipo_fixo_variavel": c.tipo_fixo_variavel,
            }
            for c in plano
        ],
        key=lambda x: x["codigo"],
    )


# ---------------------------------------------------------------------------
# Parâmetros financeiros (Configurações) — conta corrente, centro de custo e
# conta gerencial cadastráveis, além da importação de CSV do plano de contas.
# ---------------------------------------------------------------------------
class ContaCorrenteIn(BaseModel):
    banco: str
    agencia: str
    numero_conta: str
    ativo: bool = True


@router.get("/contas-correntes")
def listar_contas_correntes(session: Session = Depends(get_session)) -> list[dict]:
    contas = session.exec(select(ContaCorrente).order_by(ContaCorrente.id)).all()
    return [{**c.model_dump(), "rotulo": rotulo_conta_corrente(c)} for c in contas]


@router.post("/contas-correntes")
def criar_conta_corrente(dados: ContaCorrenteIn, session: Session = Depends(get_session)) -> dict:
    c = ContaCorrente(**dados.model_dump())
    session.add(c)
    session.commit()
    session.refresh(c)
    return {**c.model_dump(), "rotulo": rotulo_conta_corrente(c)}


@router.put("/contas-correntes/{conta_id}")
def atualizar_conta_corrente(conta_id: int, dados: ContaCorrenteIn, session: Session = Depends(get_session)) -> dict:
    c = session.get(ContaCorrente, conta_id)
    if not c:
        raise HTTPException(status_code=404, detail="Conta corrente não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(c, campo, valor)
    session.add(c)
    session.commit()
    session.refresh(c)
    return {**c.model_dump(), "rotulo": rotulo_conta_corrente(c)}


class CentroCustoIn(BaseModel):
    nome: str
    ativo: bool = True


@router.get("/centros-custo")
def listar_centros_custo(session: Session = Depends(get_session)) -> list[dict]:
    return [c.model_dump() for c in session.exec(select(CentroCusto).order_by(CentroCusto.id)).all()]


@router.post("/centros-custo")
def criar_centro_custo(dados: CentroCustoIn, session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if session.exec(select(CentroCusto).where(CentroCusto.nome == nome)).first():
        raise HTTPException(status_code=409, detail="Já existe um centro de custo com esse nome")
    c = CentroCusto(nome=nome, ativo=dados.ativo)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


@router.put("/centros-custo/{centro_id}")
def atualizar_centro_custo(centro_id: int, dados: CentroCustoIn, session: Session = Depends(get_session)) -> dict:
    c = session.get(CentroCusto, centro_id)
    if not c:
        raise HTTPException(status_code=404, detail="Centro de custo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    c.nome = nome
    c.ativo = dados.ativo
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


class PlanoContaGerencialIn(BaseModel):
    codigo: str
    nome: str
    ativa: bool = True
    participa_atividade: bool | None = None
    fluxo: bool | None = None
    tipo_fixo_variavel: str | None = None


@router.post("/plano-contas")
def criar_conta_gerencial(dados: PlanoContaGerencialIn, session: Session = Depends(get_session)) -> dict:
    codigo = dados.codigo.strip()
    if not codigo or not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Código e nome são obrigatórios")
    if session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == codigo)).first():
        raise HTTPException(status_code=409, detail="Já existe uma conta gerencial com esse código")
    conta = PlanoContaGerencial(**{**dados.model_dump(), "codigo": codigo})
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return conta.model_dump()


@router.put("/plano-contas/{conta_id}")
def atualizar_conta_gerencial(conta_id: int, dados: PlanoContaGerencialIn, session: Session = Depends(get_session)) -> dict:
    conta = session.get(PlanoContaGerencial, conta_id)
    if not conta:
        raise HTTPException(status_code=404, detail="Conta gerencial não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(conta, campo, valor)
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return conta.model_dump()


@router.get("/patrimonio")
def listar_patrimonio(session: Session = Depends(get_session)) -> dict:
    """Lista o patrimônio/imobilizado da fazenda (LISTA_DE_PATRIMONIO.csv)."""
    itens = session.exec(select(Patrimonio)).all()
    total = sum(i.valor_total or 0 for i in itens if not i.data_baixa)
    return {"itens": [i.model_dump() for i in itens], "total": len(itens), "valor_total": round(total, 2)}


@router.post("/lancamentos", status_code=201)
def criar_lancamento(dados: LancamentoIn, session: Session = Depends(get_session)) -> dict:
    """
    Cria um lançamento financeiro com um ou mais produtos/serviços (itens).
    Desconto/acréscimo ajustam o valor bruto dos itens para o valor líquido,
    que é o que efetivamente vira parcela(s). Sem data de pagamento, o
    lançamento nasce em aberto (contas a pagar/receber).
    """
    if dados.tipo not in ("receita", "despesa"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'receita' ou 'despesa'")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um produto ou serviço")

    valor_bruto = round(sum(i.valor_total for i in dados.itens), 2)
    valor_liquido = round(valor_bruto - (dados.desconto or 0) + (dados.acrescimo or 0), 2)
    if valor_liquido <= 0:
        raise HTTPException(status_code=400, detail="O valor líquido do lançamento deve ser positivo")

    ano = (dados.data_emissao or dados.data_competencia or date.today()).year
    numero_lancamento = _proximo_numero_lancamento(session, ano)
    data_competencia = dados.data_competencia or dados.data_emissao

    itens_criados = [
        LancamentoItem(
            numero_lancamento=numero_lancamento,
            tipo=dados.tipo,
            data_competencia=data_competencia,
            codigo_conta_gerencial=item.codigo_conta_gerencial,
            nome_conta_gerencial=item.nome_conta_gerencial,
            produto=item.produto,
            descricao=item.descricao,
            quantidade=item.quantidade,
            valor_unitario=item.valor_unitario,
            valor_total=item.valor_total,
        )
        for item in dados.itens
    ]

    # Resumo p/ os relatórios legados que só olham 1 conta/descrição por linha.
    descricao_resumo = ", ".join(i.produto for i in dados.itens)[:500]
    codigo_resumo = dados.itens[0].codigo_conta_gerencial if len(dados.itens) == 1 else None

    campos_comuns = dict(
        numero_lancamento=numero_lancamento,
        codigo_conta=codigo_resumo,
        descricao=descricao_resumo,
        centro_custo=dados.centro_custo,
        fornecedor_cliente=dados.fornecedor_cliente,
        responsavel=dados.responsavel,
        tipo_documento=dados.tipo_documento,
        numero_nota=dados.numero_documento,
        data_emissao=dados.data_emissao,
        data_competencia=data_competencia,
        data_prevista_entrada=dados.data_prevista_entrada,
        data_pedido=dados.data_pedido,
        entregue=dados.entregue,
        tipo=dados.tipo,
        origem="manual",
        desconto_nota=dados.desconto or None,
        acrescimo_nota=dados.acrescimo or None,
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
            valor_total=valor_liquido,
            parcela_num=1,
            parcela_total=1,
        )
        if dados.data_pagamento:
            registro.data_pagamento = dados.data_pagamento
            registro.valor_pago = dados.valor_pago
            registro.conta_bancaria = dados.conta_bancaria
            registro.numero_documento_pagamento = dados.numero_documento_pagamento
            registro.desconto_acrescimo = round((dados.valor_pago or 0) - valor_liquido, 2)
        criados.append(registro)

    for it in itens_criados:
        session.add(it)
    for c in criados:
        session.add(c)
    session.commit()
    for c in criados:
        session.refresh(c)

    return {
        "numero_lancamento": numero_lancamento,
        "ids": [c.id for c in criados],
        "valor_bruto": valor_bruto,
        "valor_liquido": valor_liquido,
    }


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
