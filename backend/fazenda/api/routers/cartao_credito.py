"""
Cartão de crédito (Controle Financeiro > Cartão de crédito) — cadastro do
cartão, lançamentos com extrato próprio por competência (fatura), fechamento
automático na leitura e pagamento reaproveitando o mesmo fluxo de baixa do
Financeiro (`criar_lancamento`). Arquivo próprio para não inchar ainda mais
`financeiro.py` — mesmo espírito de `relatorio_custo_hectare.py`: reaproveita
o prefixo `/financeiro` (FastAPI aceita vários routers com o mesmo prefixo,
ver `main.py`), registrado com as mesmas dependências de acesso.

Não substitui `ContaGerencial.data_vencimento_cartao` (forma_pagamento =
"credito") já existente — aquele continua servindo pagamento avulso no
cartão sem cadastro nenhum; este módulo é para quem quer extrato, fatura e
milhas de verdade por cartão.

Fluxo:
  1) Compra: POST /financeiro/cartoes/{id}/lancamentos — cai na fatura aberta
     da competência certa (compra até o dia de fechamento = mês corrente,
     depois = mês seguinte), ver `_competencia_da_compra`.
  2) Extrato: GET /financeiro/cartoes/{id}/extrato — fatura aberta atual (ou
     uma competência específica do histórico) + seus lançamentos; o total
     soma os lançamentos ao vivo enquanto aberta (nunca um contador guardado
     — evita drift), e usa o valor congelado quando já fechada/paga.
  3) Fechamento: preguiçoso, na leitura (mesmo padrão de
     `cronograma_aberto()` em rules/cronograma_sanitario.py) — toda vez que
     uma fatura aberta é lida e já passou do dia de fechamento, congela
     valor_total/milhas_acumuladas e vira "fechada". Também dá pra fechar
     antes na mão (POST .../fechar).
  4) Pagamento: POST /financeiro/cartoes/faturas/{fatura_id}/pagar — só numa
     fatura "fechada"; gera uma Conta a Pagar de verdade via
     `criar_lancamento` (mesmo padrão de `gerar_lancamento_recorrente`),
     então a fatura vira "paga". Nada novo no motor financeiro: a fatura
     paga é só uma ContaGerencial como qualquer outra.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.financeiro import ItemIn, LancamentoIn, criar_lancamento, rotulo_conta_corrente
from fazenda.rules import cartao_por_item
from fazenda.rules.datas import hoje_local
from fazenda.rules.parametros import regras_v2_ativas
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import CartaoCredito, ContaCorrente, FaturaCartao, LancamentoCartao, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.patrimonio import somar_meses

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


# ---------------------------------------------------------------------------
# Cadastro do cartão
# ---------------------------------------------------------------------------
class CartaoCreditoIn(BaseModel):
    apelido: str
    bandeira: Optional[str] = None
    banco_emissor: Optional[str] = None
    conta_bancaria_id: Optional[int] = None
    dia_fechamento: int
    dia_vencimento: int
    limite: Optional[float] = None
    controla_milhas: bool = False
    milhas_por_real: Optional[float] = None
    ativo: bool = True


def _validar_cartao(dados: CartaoCreditoIn) -> None:
    if not dados.apelido.strip():
        raise HTTPException(status_code=400, detail="Informe um apelido para o cartão")
    if not (1 <= dados.dia_fechamento <= 31):
        raise HTTPException(status_code=400, detail="Dia de fechamento deve estar entre 1 e 31")
    if not (1 <= dados.dia_vencimento <= 31):
        raise HTTPException(status_code=400, detail="Dia de vencimento deve estar entre 1 e 31")


def _melhor_dia_compra(dia_fechamento: int) -> int:
    """O dia logo após o fechamento tem o maior float até o próximo
    vencimento — aproximação simples (não tenta acertar meses de 28-31
    dias), só para orientar o usuário na tela de cadastro."""
    return 1 if dia_fechamento >= 31 else dia_fechamento + 1


def _dump_cartao(c: CartaoCredito) -> dict:
    return {**c.model_dump(), "melhor_dia_compra": _melhor_dia_compra(c.dia_fechamento)}


def _cartao_ou_404(session: Session, cartao_id: int, fazenda_id: int | None) -> CartaoCredito:
    c = session.get(CartaoCredito, cartao_id)
    if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Cartão não encontrado")
    return c


@router.get("/cartoes")
def listar_cartoes(session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id)) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(CartaoCredito)
    if fazenda_id is not None:
        query = query.where(CartaoCredito.fazenda_id == fazenda_id)
    cartoes = session.exec(query.order_by(CartaoCredito.apelido)).all()
    return [_dump_cartao(c) for c in cartoes]


@router.get("/cartoes/{cartao_id}")
def detalhe_cartao(
    cartao_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cartao = _cartao_ou_404(session, cartao_id, fazenda_id)
    faturas = session.exec(select(FaturaCartao).where(FaturaCartao.cartao_id == cartao.id)).all()
    milhas_totais = sum(f.milhas_acumuladas or 0 for f in faturas if f.status in ("fechada", "paga"))
    return {**_dump_cartao(cartao), "milhas_totais": milhas_totais if cartao.controla_milhas else None}


@router.post("/cartoes", status_code=201)
def criar_cartao(
    dados: CartaoCreditoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    # BUG DE SEGURANÇA CORRIGIDO (achado 17): a criação gravava pela
    # dependência TOLERANTE, ao contrário de criar_lancamento/criar_pedido e
    # dos cadastros financeiros irmãos (conta corrente, centro de custo, plano
    # de contas), que já usam a estrita. Um cartão com `fazenda_id=NULL` é
    # pior que um catálogo órfão: a fatura, o lançamento e a conta bancária
    # vinculada pendurados nele passam a não pertencer a fazenda nenhuma, e a
    # checagem de posse da ContaCorrente logo abaixo perde o efeito — com
    # `fazenda_id` None, o `if fazenda_id is not None` cai e qualquer conta
    # bancária serve, inclusive a de outro tenant.
    _validar_cartao(dados)
    if dados.conta_bancaria_id:
        # BUG DE SEGURANÇA CORRIGIDO: sem o filtro de fazenda_id, um cartão
        # podia ser vinculado a uma ContaCorrente de OUTRA fazenda.
        conta_bancaria = session.get(ContaCorrente, dados.conta_bancaria_id)
        if not conta_bancaria or (fazenda_id is not None and conta_bancaria.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Conta bancária não encontrada")
    c = CartaoCredito(**{**dados.model_dump(), "apelido": dados.apelido.strip()}, fazenda_id=fazenda_id)
    session.add(c)
    session.commit()
    session.refresh(c)
    return _dump_cartao(c)


@router.put("/cartoes/{cartao_id}")
def atualizar_cartao(
    cartao_id: int, dados: CartaoCreditoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    c = _cartao_ou_404(session, cartao_id, fazenda_id)
    _validar_cartao(dados)
    if dados.conta_bancaria_id:
        conta_bancaria = session.get(ContaCorrente, dados.conta_bancaria_id)
        if not conta_bancaria or (fazenda_id is not None and conta_bancaria.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Conta bancária não encontrada")
    for campo, valor in dados.model_dump().items():
        setattr(c, campo, valor)
    c.apelido = c.apelido.strip()
    session.add(c)
    session.commit()
    session.refresh(c)
    return _dump_cartao(c)


# ---------------------------------------------------------------------------
# Fatura — resolução de competência, criação preguiçosa e fechamento
# ---------------------------------------------------------------------------
def _dia_no_mes(ano: int, mes: int, dia: int) -> date:
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(dia, ultimo_dia))


def _competencia_da_compra(cartao: CartaoCredito, data_compra: date) -> date:
    """Mês de referência (dia 1) da fatura que esta compra cai — depois do
    dia de fechamento do mês, a compra já entra na fatura seguinte."""
    referencia = data_compra if data_compra.day <= cartao.dia_fechamento else somar_meses(data_compra, 1)
    return date(referencia.year, referencia.month, 1)


def _obter_ou_criar_fatura(session: Session, cartao: CartaoCredito, referencia: date) -> FaturaCartao:
    competencia = f"{referencia.year:04d}-{referencia.month:02d}"
    existente = session.exec(
        select(FaturaCartao).where(FaturaCartao.cartao_id == cartao.id).where(FaturaCartao.competencia == competencia)
    ).first()
    if existente:
        return existente
    nova = FaturaCartao(
        fazenda_id=cartao.fazenda_id, cartao_id=cartao.id, competencia=competencia,
        data_fechamento=_dia_no_mes(referencia.year, referencia.month, cartao.dia_fechamento),
        data_vencimento=_dia_no_mes(referencia.year, referencia.month, cartao.dia_vencimento),
    )
    session.add(nova)
    session.commit()
    session.refresh(nova)
    return nova


def _congelar_fatura(session: Session, fatura: FaturaCartao, cartao: CartaoCredito) -> FaturaCartao:
    itens = session.exec(select(LancamentoCartao).where(LancamentoCartao.fatura_id == fatura.id)).all()
    fatura.valor_total = round(sum(i.valor for i in itens), 2)
    fatura.milhas_acumuladas = (
        int(fatura.valor_total * cartao.milhas_por_real) if cartao.controla_milhas and cartao.milhas_por_real else None
    )
    fatura.status = "fechada"
    fatura.atualizado_em = datetime.utcnow()
    session.add(fatura)
    session.commit()
    session.refresh(fatura)
    return fatura


def _fechar_se_vencida(session: Session, fatura: FaturaCartao, cartao: CartaoCredito, hoje: date) -> FaturaCartao:
    """Congela e fecha quando o dia de fechamento já passou — preguiçoso, na
    leitura (mesmo padrão de `cronograma_aberto()`).

    Bug real corrigido aqui: a comparação era `hoje < data_fechamento`, ou
    seja, a fatura já congelava ao ALCANÇAR o dia de fechamento — em
    contradição com a própria regra de qual fatura uma compra pertence, em
    `_competencia_da_compra` (`data_compra.day <= cartao.dia_fechamento`,
    documentada acima como "compra até o dia de fechamento = mês corrente":
    inclusivo). `criar_lancamento_cartao` busca/cria a fatura e SÓ DEPOIS
    chama esta função antes de inserir o item — com `<`, no próprio dia do
    fechamento a fatura fechava sozinha antes de aceitar o lançamento que,
    pela regra de competência, deveria caber nela: toda compra lançada
    exatamente no dia do fechamento do cartão vinha rejeitada com "A fatura
    desta competência já foi fechada", e o extrato lido nesse mesmo dia
    congelava a fatura um dia mais cedo do que devido. `<=` mantém a fatura
    aberta durante todo o dia de fechamento; ela só congela a partir do dia
    seguinte, como o resto do módulo já documentava."""
    if fatura.status != "aberta" or hoje <= fatura.data_fechamento:
        return fatura
    return _congelar_fatura(session, fatura, cartao)


# Colunas novas do PR 5 (cartão por item): só aparecem com a flag
# `financeiro_regras_v2` — sem ela, o fluxo do cartão responde as mesmas chaves de antes.
_CAMPOS_FATURA_V2 = ("valor_pago", "desconto_acrescimo")
_CAMPOS_COMPRA_V2 = ("numero_lancamento",)


def _sem_campos_v2(d: dict, campos: tuple[str, ...], regras_v2: bool) -> dict:
    if not regras_v2:
        for campo in campos:
            d.pop(campo, None)
    return d


def _dump_compra(compra: LancamentoCartao, regras_v2: bool) -> dict:
    return _sem_campos_v2(compra.model_dump(), _CAMPOS_COMPRA_V2, regras_v2)


def _dump_fatura(session: Session, fatura: FaturaCartao) -> dict:
    d = _sem_campos_v2(fatura.model_dump(), _CAMPOS_FATURA_V2, regras_v2_ativas(session, fatura.fazenda_id))
    if fatura.status == "aberta":
        itens = session.exec(select(LancamentoCartao).where(LancamentoCartao.fatura_id == fatura.id)).all()
        d["valor_total"] = round(sum(i.valor for i in itens), 2)
    return d


@router.get("/cartoes/{cartao_id}/extrato")
def extrato_cartao(
    cartao_id: int, competencia: Optional[str] = None, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Sem `competencia`: fatura aberta atual (criando-a se este cartão ainda
    não tem nenhuma compra no mês corrente). Com `competencia` ("YYYY-MM"):
    uma fatura específica do histórico — 404 se nunca existiu."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cartao = _cartao_ou_404(session, cartao_id, fazenda_id)
    hoje = hoje_local()
    if competencia:
        fatura = session.exec(
            select(FaturaCartao).where(FaturaCartao.cartao_id == cartao.id).where(FaturaCartao.competencia == competencia)
        ).first()
        if not fatura:
            raise HTTPException(status_code=404, detail="Fatura não encontrada para esta competência")
    else:
        fatura = _obter_ou_criar_fatura(session, cartao, _competencia_da_compra(cartao, hoje))
    fatura = _fechar_se_vencida(session, fatura, cartao, hoje)
    itens = session.exec(
        select(LancamentoCartao).where(LancamentoCartao.fatura_id == fatura.id).order_by(LancamentoCartao.data_compra)
    ).all()
    regras_v2 = regras_v2_ativas(session, cartao.fazenda_id)
    return {"cartao": _dump_cartao(cartao), "fatura": _dump_fatura(session, fatura), "lancamentos": [_dump_compra(i, regras_v2) for i in itens]}


@router.get("/cartoes/{cartao_id}/faturas")
def listar_faturas_cartao(
    cartao_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cartao = _cartao_ou_404(session, cartao_id, fazenda_id)
    hoje = hoje_local()
    faturas = session.exec(
        select(FaturaCartao).where(FaturaCartao.cartao_id == cartao.id).order_by(FaturaCartao.competencia.desc())
    ).all()
    faturas = [_fechar_se_vencida(session, f, cartao, hoje) for f in faturas]
    return [_dump_fatura(session, f) for f in faturas]


def _fatura_ou_404(session: Session, fatura_id: int, fazenda_id: int | None) -> FaturaCartao:
    fatura = session.get(FaturaCartao, fatura_id)
    if not fatura or (fazenda_id is not None and fatura.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    return fatura


@router.post("/cartoes/faturas/{fatura_id}/fechar")
def fechar_fatura_cartao(
    fatura_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Fecha a fatura antes do dia de fechamento normal, por vontade do
    usuário (ex.: já sabe que não vai lançar mais nada nesse mês)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    fatura = _fatura_ou_404(session, fatura_id, fazenda_id)
    if fatura.status != "aberta":
        raise HTTPException(status_code=400, detail="Esta fatura já não está mais aberta")
    cartao = _cartao_ou_404(session, fatura.cartao_id, fazenda_id)
    fatura = _congelar_fatura(session, fatura, cartao)
    return _dump_fatura(session, fatura)


# ---------------------------------------------------------------------------
# Lançamentos (compras) no cartão
# ---------------------------------------------------------------------------
class LancamentoCartaoIn(BaseModel):
    data_compra: date
    descricao: str
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    centro_custo: Optional[str] = None
    valor: float
    parcela_num: Optional[int] = None
    parcela_total: Optional[int] = None
    observacao: Optional[str] = None


@router.post("/cartoes/{cartao_id}/lancamentos", status_code=201)
def criar_lancamento_cartao(
    cartao_id: int, dados: LancamentoCartaoIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    cartao = _cartao_ou_404(session, cartao_id, fazenda_id)
    if not dados.descricao.strip():
        raise HTTPException(status_code=400, detail="Descrição é obrigatória")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser positivo")
    fatura = _obter_ou_criar_fatura(session, cartao, _competencia_da_compra(cartao, dados.data_compra))
    fatura = _fechar_se_vencida(session, fatura, cartao, hoje_local())
    if fatura.status != "aberta":
        raise HTTPException(status_code=400, detail="A fatura desta competência já foi fechada — não é mais possível lançar nela")
    lanc = LancamentoCartao(
        **{**dados.model_dump(exclude={"descricao"}), "descricao": dados.descricao.strip()},
        cartao_id=cartao.id, fatura_id=fatura.id, fazenda_id=fazenda_id,
        usuario_id=user.id if isinstance(user, Usuario) else None,
    )
    session.add(lanc)
    regras_v2 = regras_v2_ativas(session, cartao.fazenda_id)
    if regras_v2:
        # Fase A, PR 5: a compra nasce como NOTA em aberto (competência = data
        # da compra, vencimento = o da fatura) — entra na DRE pela conta dela,
        # em Contas a pagar e no Caixa Real; só se paga pela fatura.
        session.flush()
        cartao_por_item.nova_nota_da_compra(session, cartao, fatura, lanc, usuario_id=lanc.usuario_id)
    session.commit()
    session.refresh(lanc)
    return {**_dump_compra(lanc, regras_v2), "competencia": fatura.competencia}


# ---------------------------------------------------------------------------
# Pagamento da fatura — reaproveita `criar_lancamento` (mesmo padrão de
# `gerar_lancamento_recorrente`, ver financeiro.py)
# ---------------------------------------------------------------------------
class PagarFaturaCartaoIn(BaseModel):
    data_pagamento: Optional[date] = None
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    centro_custo: Optional[str] = None
    # Só com as regras v2 (PR 5): o que foi pago de fato (padrão = o total da
    # fatura; a diferença é rateada entre as notas) e o comprovante.
    valor_pago: Optional[float] = None
    numero_documento_pagamento: Optional[str] = None


@router.post("/cartoes/faturas/{fatura_id}/pagar", status_code=201)
def pagar_fatura_cartao(
    fatura_id: int, dados: PagarFaturaCartaoIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    fatura = _fatura_ou_404(session, fatura_id, fazenda_id)
    cartao = _cartao_ou_404(session, fatura.cartao_id, fazenda_id)
    fatura = _fechar_se_vencida(session, fatura, cartao, hoje_local())
    if fatura.status == "aberta":
        raise HTTPException(status_code=400, detail="Feche a fatura antes de pagar (ou aguarde o dia de fechamento)")
    if fatura.status == "paga":
        raise HTTPException(status_code=400, detail="Esta fatura já foi paga")
    if not fatura.valor_total or fatura.valor_total <= 0:
        raise HTTPException(status_code=400, detail="Fatura sem lançamentos — nada a pagar")
    if regras_v2_ativas(session, fazenda_id):
        return _pagar_fatura_v2(session, fatura, cartao, dados, user)

    conta_bancaria_str = None
    if cartao.conta_bancaria_id:
        conta = session.get(ContaCorrente, cartao.conta_bancaria_id)
        if conta:
            conta_bancaria_str = rotulo_conta_corrente(conta)

    data_pagamento = dados.data_pagamento or hoje_local()
    item = ItemIn(
        codigo_conta_gerencial=dados.codigo_conta_gerencial, nome_conta_gerencial=dados.nome_conta_gerencial,
        produto=f"Fatura {cartao.apelido} — {fatura.competencia}", valor_total=fatura.valor_total,
    )
    lanc = LancamentoIn(
        tipo="despesa", itens=[item], centro_custo=dados.centro_custo,
        fornecedor_cliente=cartao.banco_emissor or cartao.apelido,
        data_emissao=data_pagamento, data_vencimento=fatura.data_vencimento,
        data_pagamento=data_pagamento, valor_pago=fatura.valor_total,
        conta_bancaria=conta_bancaria_str, forma_pagamento="transferencia" if conta_bancaria_str else None,
    )
    resultado = criar_lancamento(dados=lanc, session=session, user=user, fazenda_id=fazenda_id)

    fatura.status = "paga"
    fatura.numero_lancamento = resultado["numero_lancamento"]
    fatura.atualizado_em = datetime.utcnow()
    session.add(fatura)
    session.commit()
    session.refresh(fatura)
    return {**_dump_fatura(session, fatura), "lancamento": resultado}


def _conta_do_cartao(session: Session, cartao: CartaoCredito) -> tuple[str | None, int | None]:
    if cartao.conta_bancaria_id:
        conta = session.get(ContaCorrente, cartao.conta_bancaria_id)
        if conta and conta.fazenda_id == cartao.fazenda_id:
            return rotulo_conta_corrente(conta), conta.id
    return None, None


def _pagar_fatura_v2(
    session: Session, fatura: FaturaCartao, cartao: CartaoCredito, dados: PagarFaturaCartaoIn, user,
) -> dict:
    """Regras v2 (PR 5): pagar a fatura = baixar TODAS as notas das compras de
    uma vez (mesma data, conta e forma). Pago diferente do total: a diferença é
    rateada entre as notas em centavos (sobra na última), como na fatura de
    fornecedor, e vira `desconto_acrescimo` de cada uma (juros/desconto em
    Outras, PR 7). Nenhuma nota genérica."""
    usuario_id = user.id if isinstance(user, Usuario) else None
    notas = cartao_por_item.garantir_notas(session, cartao, fatura, usuario_id)
    if any(n.data_pagamento is not None for n in notas):
        session.rollback()
        raise HTTPException(status_code=409, detail="Há nota desta fatura já baixada — confira a fatura antes de pagar.")
    soma = round(sum(n.valor_total or 0 for n in notas), 2)
    if round(soma - (fatura.valor_total or 0), 2) != 0:
        session.rollback()
        raise HTTPException(status_code=409, detail=(
            f"As notas da fatura somam R$ {soma:.2f} e a fatura fechou em R$ {fatura.valor_total:.2f}. "
            "Confira as compras antes de pagar."))
    pago = round(dados.valor_pago if dados.valor_pago is not None else soma, 2)
    if pago <= 0:
        session.rollback()
        raise HTTPException(status_code=400, detail="O valor pago deve ser maior que zero.")
    data_pagamento = dados.data_pagamento or hoje_local()
    rotulo, conta_id = _conta_do_cartao(session, cartao)
    cotas = cartao_por_item.ratear_diferenca([n.valor_total or 0 for n in notas], pago)
    try:
        for nota, cota in zip(notas, cotas):
            nota.data_pagamento = data_pagamento
            nota.valor_pago = round((nota.valor_total or 0) + cota, 2)
            nota.desconto_acrescimo = cota
            nota.diferenca_tipo = None
            nota.conta_bancaria = rotulo
            nota.conta_corrente_id = conta_id
            nota.forma_pagamento = "transferencia" if rotulo else None
            nota.numero_documento_pagamento = dados.numero_documento_pagamento
            nota.atualizado_em = datetime.utcnow()
            session.add(nota)
        fatura.status = "paga"
        fatura.valor_pago = pago
        fatura.desconto_acrescimo = round(pago - soma, 2)
        fatura.atualizado_em = datetime.utcnow()
        session.add(fatura)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(fatura)
    return {
        **_dump_fatura(session, fatura), "lancamento": None,
        "notas_pagas": [n.numero_lancamento for n in notas], "diferenca": round(pago - soma, 2),
    }


class EstornarFaturaCartaoIn(BaseModel):
    motivo: str


@router.post("/cartoes/faturas/{fatura_id}/estornar-pagamento")
def estornar_pagamento_fatura_cartao(
    fatura_id: int, dados: EstornarFaturaCartaoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Regras v2 (PR 5): desfaz o pagamento da fatura — as notas das compras
    voltam a "em aberto" juntas e a fatura volta a "fechada" (uma nota de
    fatura não se estorna sozinha: recusa 409). Fatura paga pela nota genérica
    antiga: estorne a nota genérica no Financeiro."""
    if not regras_v2_ativas(session, fazenda_id):
        raise HTTPException(status_code=409, detail="Disponível só com as regras novas do Financeiro.")
    if not (dados.motivo or "").strip():
        raise HTTPException(status_code=400, detail="Informe o motivo do estorno.")
    fatura = _fatura_ou_404(session, fatura_id, fazenda_id)
    if fatura.status != "paga":
        raise HTTPException(status_code=409, detail="Esta fatura não está paga.")
    if fatura.numero_lancamento:
        raise HTTPException(status_code=409, detail=(
            f"Esta fatura foi paga pela nota {fatura.numero_lancamento} (regras antigas): estorne essa nota no Financeiro."))
    notas = cartao_por_item.notas_da_fatura(session, fatura)
    for nota in notas:
        nota.data_pagamento = nota.valor_pago = nota.conta_bancaria = nota.conta_corrente_id = None
        nota.forma_pagamento = nota.numero_documento_pagamento = nota.desconto_acrescimo = nota.diferenca_tipo = None
        nota.atualizado_em = datetime.utcnow()
        session.add(nota)
    fatura.status, fatura.valor_pago, fatura.desconto_acrescimo = "fechada", None, None
    fatura.atualizado_em = datetime.utcnow()
    session.add(fatura)
    session.commit()
    session.refresh(fatura)
    return {**_dump_fatura(session, fatura), "notas_estornadas": [n.numero_lancamento for n in notas]}
