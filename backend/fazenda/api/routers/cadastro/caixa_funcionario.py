"""
Caixa dos funcionários — Fase 1 (caixa individual).

Cada colaborador (CLT, empreita, contrato, diária) tem um saldo a favor, que é a
SOMA dos seus movimentos (`CaixaMovimento`). Só o administrador lança e edita.

Regras (combinadas com o dono):
- Entradas da fazenda (depósito, bonificação, comissão, outro): sempre em R$, com
  motivo. Cada uma gera uma despesa de pessoal já baixada no Financeiro (o
  dinheiro é "colocado no caixa" na data), com número de lançamento.
- Retirada: bloqueada acima do saldo. Gera um recibo numerado (CX-AAAA-nnnnn). Não
  cria despesa nova: o gasto já foi reconhecido quando o dinheiro entrou.
- Nada é editado: erro se corrige por ESTORNO (movimento contrário, original
  continua visível). Exclusão só do último movimento da pessoa, se não for um
  estorno nem tiver sido estornado, e só por administrador.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import CaixaMovimento, CaixaRetencao, ContaGerencial, Pessoa
from fazenda.rules import caixa_funcionario as regras
from fazenda.rules import caixa_time as regras_time
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro

router = APIRouter(prefix="/caixa-funcionarios", tags=["Caixa dos funcionários"])

TIPOS_ENTRADA = {
    "deposito": "Depósito da fazenda",
    "bonificacao": "Bonificação por produtividade",
    "comissao": "Comissão",
    "outro": "Outro tipo",
}
FORMAS_RETIRADA = ["pix", "dinheiro", "transferencia", "debito", "credito", "boleto"]
TIPO_DOC_ENTRADA = "Caixa do funcionário"
TIPO_DOC_ESTORNO = "Estorno caixa do funcionário"

_grupos_da_pessoa = regras.grupos_da_pessoa


def _movimentos_da_pessoa(session: Session, pessoa_id: int, fazenda_id: int | None) -> list[CaixaMovimento]:
    query = select(CaixaMovimento).where(CaixaMovimento.pessoa_id == pessoa_id)
    if fazenda_id is not None:
        query = query.where(CaixaMovimento.fazenda_id == fazenda_id)
    return list(session.exec(query.order_by(CaixaMovimento.data, CaixaMovimento.id)).all())


def _brl(valor: float) -> str:
    """1234.5 -> "1.234,50" (sem depender do locale do servidor)."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _saldo(movimentos: list[CaixaMovimento]) -> float:
    return round(sum(m.valor for m in movimentos), 2)


def _pessoa_ou_404(session: Session, pessoa_id: int, fazenda_id: int | None) -> Pessoa:
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa or (fazenda_id is not None and pessoa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    return pessoa


def _movimento_ou_404(session: Session, pessoa_id: int, movimento_id: int, fazenda_id: int | None) -> CaixaMovimento:
    m = session.get(CaixaMovimento, movimento_id)
    if not m or m.pessoa_id != pessoa_id or (fazenda_id is not None and m.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Movimento não encontrado")
    return m


def _serializar_movimentos(movimentos: list[CaixaMovimento]) -> list[dict]:
    """Do mais recente ao mais antigo, com saldo corrente e as flags que a tela usa."""
    estornados = {m.estorna_id for m in movimentos if m.estorna_id}
    ultimo_id = max((m.id for m in movimentos), default=None)
    acumulado = 0.0
    saldo_depois: dict[int, float] = {}
    for m in movimentos:  # ordem cronológica (data, id)
        acumulado = round(acumulado + m.valor, 2)
        saldo_depois[m.id] = acumulado
    saidas = []
    for m in sorted(movimentos, key=lambda x: (x.data, x.id), reverse=True):
        eh_estorno = m.tipo == "estorno"
        estornado = m.id in estornados
        saidas.append({
            **m.model_dump(),
            "saldo_depois": saldo_depois[m.id],
            "estornado": estornado,
            "eh_estorno": eh_estorno,
            "pode_estornar": not eh_estorno and not estornado,
            # Exclusão: só o último movimento, que não seja estorno e não tenha sido estornado.
            "pode_excluir": m.id == ultimo_id and not eh_estorno and not estornado,
        })
    return saidas


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
@router.get("/retencao-opcoes")
def opcoes_de_retencao_no_pagamento(
    valor: float, pessoa_id: int | None = None, lancamento_id: int | None = None, data: date | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    """Para a janela de pagamento de quem não é CLT: dá para reter? qual a sugestão? Passe `pessoa_id`
    (diária) ou `lancamento_id` (parcela de contrato/empreita — a pessoa vem do contrato)."""
    from fazenda.models import ContaGerencial

    fazenda_id = fazenda_id_seguro(fazenda_id)
    if pessoa_id is None and lancamento_id is not None:
        conta = session.get(ContaGerencial, lancamento_id)
        if conta is None or (fazenda_id is not None and conta.fazenda_id != fazenda_id):
            raise HTTPException(status_code=404, detail="Lançamento não encontrado")
        pessoa_id = regras.pessoa_da_conta_paga(session, conta)
        if pessoa_id is None:
            return {"disponivel": False, "motivo": None, "pessoa": None}
    if pessoa_id is None:
        raise HTTPException(status_code=400, detail="Informe a pessoa ou o lançamento.")
    return regras.opcoes_retencao_pagamento(session, pessoa_id, fazenda_id, valor, data)


@router.get("")
def listar_caixas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    """Todas as pessoas ativas da fazenda com o saldo do caixa individual."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Pessoa).where(Pessoa.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(Pessoa.fazenda_id == fazenda_id)
    pessoas = [p for p in session.exec(query.order_by(Pessoa.nome)).all() if _grupos_da_pessoa(p)]

    query_mov = select(CaixaMovimento)
    if fazenda_id is not None:
        query_mov = query_mov.where(CaixaMovimento.fazenda_id == fazenda_id)
    por_pessoa: dict[int, list[CaixaMovimento]] = {}
    for m in session.exec(query_mov).all():
        por_pessoa.setdefault(m.pessoa_id, []).append(m)

    linhas = []
    for p in pessoas:
        movs = por_pessoa.get(p.id, [])
        linhas.append({
            "pessoa_id": p.id, "nome": p.nome, "tipo": p.tipo, "grupos": _grupos_da_pessoa(p),
            "saldo": _saldo(movs), "movimentos": len(movs),
            "ultimo_movimento": max((m.data for m in movs), default=None),
        })
    return {
        "pessoas": linhas,
        "total_devido": round(sum(l["saldo"] for l in linhas), 2),
        "tipos_entrada": TIPOS_ENTRADA,
    }


# ---------------------------------------------------------------------------
# Retenção em folha (Fase 2)
# ---------------------------------------------------------------------------
def _dados_retencao(session: Session, pessoa: Pessoa, fazenda_id: int | None) -> dict:
    cfg = regras.retencao_da_pessoa(session, pessoa.id, fazenda_id)
    anexado = regras.termo_anexado(session, pessoa.id, fazenda_id)
    return {
        "pessoa": {"id": pessoa.id, "nome": pessoa.nome, "tipo": pessoa.tipo, "grupos": _grupos_da_pessoa(pessoa),
                   "salario_base": pessoa.salario_base},
        "config": cfg.model_dump() if cfg else None,
        "acumulado": regras.acumulado_retido(session, pessoa.id, fazenda_id),
        "termo_anexado": anexado,
        "termo_pendente": regras.termo_pendente(cfg, anexado),
    }


@router.get("/retencoes")
def listar_retencoes(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(CaixaRetencao)
    if fazenda_id is not None:
        query = query.where(CaixaRetencao.fazenda_id == fazenda_id)
    linhas = []
    for cfg in session.exec(query).all():
        pessoa = session.get(Pessoa, cfg.pessoa_id)
        if pessoa is None:
            continue
        linhas.append(_dados_retencao(session, pessoa, fazenda_id))
    return {"retencoes": linhas}


@router.get("/pendencias")
def pendencias_do_caixa(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    """O que o caixa está devendo de documento: alimenta o aviso do Fechamento da folha."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    return {"termos_pendentes": regras.termos_pendentes(session, fazenda_id)}


@router.get("/rodape-recibos")
def rodape_dos_recibos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _: object = Depends(exigir_admin),
) -> dict:
    """Rodapé do holerite/recibo (SÓ administrador): o saldo individual e a parte estimada
    no caixa do time. `por_folha` traz a fotografia de cada folha já paga (o que valia no
    ato do pagamento); `por_pessoa` é o saldo de hoje, para folha/recibo ainda em aberto."""
    import json as _json
    from fazenda.models import FolhaPagamento

    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(FolhaPagamento).where(FolhaPagamento.caixa_congelado != None)  # noqa: E711
    if fazenda_id is not None:
        query = query.where(FolhaPagamento.fazenda_id == fazenda_id)
    por_folha = {f.id: _json.loads(f.caixa_congelado) for f in session.exec(query).all()}
    return {"por_folha": por_folha, "por_pessoa": regras_time.resumos_para_recibo(session, fazenda_id)}


@router.get("/{pessoa_id}/extrato")
def extrato_mensal(
    pessoa_id: int, mes: str, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id), _: object = Depends(exigir_admin),
) -> dict:
    """Extrato do mês (AAAA-MM): saldo anterior, movimentos, saldo final e a parte
    estimada nos caixas do time. Base do PDF mensal."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = _pessoa_ou_404(session, pessoa_id, fazenda_id)
    try:
        ano, m = (int(x) for x in mes.split("-"))
        inicio = date(ano, m, 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Mês inválido: use AAAA-MM") from None
    fim = date(ano + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    movs = _movimentos_da_pessoa(session, pessoa_id, fazenda_id)
    anterior = round(sum(x.valor for x in movs if x.data < inicio), 2)
    do_mes = [x for x in movs if inicio <= x.data <= fim]
    return {
        "pessoa": {"id": pessoa.id, "nome": pessoa.nome, "tipo": pessoa.tipo},
        "mes": mes, "saldo_anterior": anterior,
        "movimentos": [{**x.model_dump(), "estornado": any(y.estorna_id == x.id for y in movs)} for x in do_mes],
        "saldo_final": round(anterior + sum(x.valor for x in do_mes), 2),
        "times": regras_time.resumos_para_recibo(session, fazenda_id, [pessoa_id]).get(pessoa_id, {}).get("times", []),
    }


@router.get("/{pessoa_id}/retencao")
def obter_retencao(
    pessoa_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id), _: object = Depends(exigir_admin),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    return _dados_retencao(session, _pessoa_ou_404(session, pessoa_id, fazenda_id), fazenda_id)


class RetencaoIn(BaseModel):
    forma: str  # fixo | percentual
    valor: float
    inicio: date
    fim: date | None = None
    teto: float | None = None
    autorizada: bool = False
    destino: str = "individual"  # individual | time | dividir
    time_id: int | None = None
    pct_time: float = 50.0


@router.put("/{pessoa_id}/retencao")
def salvar_retencao(
    pessoa_id: int, dados: RetencaoIn, session: Session = Depends(get_session), user=Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """Cria ou atualiza o combinado de retenção (um por pessoa)."""
    pessoa = _pessoa_ou_404(session, pessoa_id, fazenda_id)
    if dados.forma not in ("fixo", "percentual"):
        raise HTTPException(status_code=400, detail="Forma inválida: use valor fixo ou percentual")
    if dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Informe um valor maior que zero")
    if dados.forma == "percentual" and dados.valor > 100:
        raise HTTPException(status_code=400, detail="O percentual não pode passar de 100%")
    if dados.teto is not None and dados.teto <= 0:
        raise HTTPException(status_code=400, detail="O teto precisa ser maior que zero (ou fique em branco)")
    if dados.fim is not None and dados.fim < dados.inicio:
        raise HTTPException(status_code=400, detail="O fim da vigência não pode ser antes do início")
    if dados.destino not in ("individual", "time", "dividir"):
        raise HTTPException(status_code=400, detail="Destino inválido")
    time_id = None
    if dados.destino != "individual":
        from fazenda.models import CaixaTime
        t = session.get(CaixaTime, dados.time_id) if dados.time_id else None
        if t is None or t.fazenda_id != fazenda_id or not t.ativo:
            raise HTTPException(status_code=400, detail="Escolha um caixa do time ativo para receber a retenção")
        time_id = t.id
    if dados.destino == "dividir" and not 0 < dados.pct_time < 100:
        raise HTTPException(status_code=400, detail="A parte do time deve ficar entre 0 e 100%")
    cfg = regras.retencao_da_pessoa(session, pessoa_id, fazenda_id)
    if cfg is None:
        cfg = CaixaRetencao(fazenda_id=fazenda_id, pessoa_id=pessoa_id, inicio=dados.inicio)
    cfg.destino, cfg.time_id, cfg.pct_time = dados.destino, time_id, dados.pct_time
    cfg.forma, cfg.valor, cfg.inicio, cfg.fim, cfg.teto = dados.forma, round(dados.valor, 2), dados.inicio, dados.fim, dados.teto
    if dados.autorizada and not cfg.autorizada:
        cfg.autorizada_em = date.today()
        cfg.revogada_em = None  # nova autorização reabre a vigência
    cfg.autorizada = dados.autorizada
    cfg.atualizado_em = datetime.utcnow()
    cfg.usuario_id = usuario_id_seguro(user)
    session.add(cfg)
    session.commit()
    return _dados_retencao(session, pessoa, fazenda_id)


class PausaIn(BaseModel):
    pausada: bool


@router.post("/{pessoa_id}/retencao/pausar")
def pausar_retencao(
    pessoa_id: int, dados: PausaIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    pessoa = _pessoa_ou_404(session, pessoa_id, fazenda_id)
    cfg = regras.retencao_da_pessoa(session, pessoa_id, fazenda_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Esta pessoa não tem retenção combinada")
    cfg.pausada = dados.pausada
    cfg.atualizado_em = datetime.utcnow()
    session.add(cfg)
    session.commit()
    return _dados_retencao(session, pessoa, fazenda_id)


@router.post("/{pessoa_id}/retencao/revogar")
def revogar_retencao(
    pessoa_id: int, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """O funcionário revogou a autorização: vale a partir do MÊS SEGUINTE (a vigência
    termina no último dia do mês corrente). O que já foi retido continua no caixa."""
    pessoa = _pessoa_ou_404(session, pessoa_id, fazenda_id)
    cfg = regras.retencao_da_pessoa(session, pessoa_id, fazenda_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Esta pessoa não tem retenção combinada")
    hoje = date.today()
    cfg.revogada_em = (date(hoje.year + (hoje.month == 12), hoje.month % 12 + 1, 1) - timedelta(days=1))
    cfg.atualizado_em = datetime.utcnow()
    session.add(cfg)
    session.commit()
    return _dados_retencao(session, pessoa, fazenda_id)


@router.get("/{pessoa_id}")
def obter_caixa(
    pessoa_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id), _: object = Depends(exigir_admin),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = _pessoa_ou_404(session, pessoa_id, fazenda_id)
    movs = _movimentos_da_pessoa(session, pessoa_id, fazenda_id)
    return {
        "pessoa": {"id": pessoa.id, "nome": pessoa.nome, "tipo": pessoa.tipo, "grupos": _grupos_da_pessoa(pessoa)},
        "saldo": _saldo(movs),
        "movimentos": _serializar_movimentos(movs),
    }


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------
class EntradaIn(BaseModel):
    pessoa_ids: list[int]
    tipo: str  # deposito | bonificacao | comissao | outro
    data: date
    motivo: str
    valor: float | None = None  # por pessoa; opcional em comissão (calculado de base × %)
    base_valor: float | None = None
    percentual: float | None = None
    conta_bancaria: str | None = None


@router.post("/entradas")
def lancar_entradas(
    dados: EntradaIn, session: Session = Depends(get_session), user=Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """Lança a mesma entrada para uma ou mais pessoas (o valor é POR pessoa)."""
    if dados.tipo not in TIPOS_ENTRADA:
        raise HTTPException(status_code=400, detail="Tipo de entrada inválido")
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo da entrada")
    if not dados.pessoa_ids:
        raise HTTPException(status_code=400, detail="Escolha ao menos uma pessoa")
    valor = dados.valor
    if dados.tipo == "comissao" and dados.base_valor is not None and dados.percentual is not None:
        valor = round(dados.base_valor * dados.percentual / 100, 2)
        motivo = f"{motivo} · base R$ {_brl(dados.base_valor)} × {dados.percentual:g}%"
    if valor is None or valor <= 0:
        raise HTTPException(status_code=400, detail="Informe um valor maior que zero")
    valor = round(valor, 2)

    pessoas = [_pessoa_ou_404(session, pid, fazenda_id) for pid in dict.fromkeys(dados.pessoa_ids)]
    usuario_id = usuario_id_seguro(user)
    criados: list[dict] = []
    for pessoa in pessoas:
        numero = _proximo_numero_lancamento(session, dados.data.year)
        conta = ContaGerencial(
            numero_lancamento=numero,
            descricao=f"{TIPOS_ENTRADA[dados.tipo]} · {pessoa.nome} · {motivo}"[:500],
            data_vencimento=dados.data, data_competencia=dados.data.replace(day=1),
            fornecedor_cliente=pessoa.nome, tipo_documento=TIPO_DOC_ENTRADA, centro_custo="Pecuária Leiteira",
            valor_total=valor, parcela_num=1, parcela_total=1, tipo="despesa", origem="auto",
            # O dinheiro é colocado no caixa na data: despesa reconhecida e baixada.
            data_pagamento=dados.data, valor_pago=valor,
            conta_bancaria=dados.conta_bancaria or None, forma_pagamento="caixa_funcionario",
            fazenda_id=fazenda_id,
        )
        session.add(conta)
        session.flush()
        mov = CaixaMovimento(
            fazenda_id=fazenda_id, pessoa_id=pessoa.id, tipo=dados.tipo, valor=valor, data=dados.data, motivo=motivo,
            base_valor=dados.base_valor if dados.tipo == "comissao" else None,
            percentual=dados.percentual if dados.tipo == "comissao" else None,
            lancamento_id=conta.id, numero_lancamento=numero, usuario_id=usuario_id,
        )
        session.add(mov)
        session.flush()
        criados.append({"pessoa_id": pessoa.id, "nome": pessoa.nome, "movimento_id": mov.id, "numero_lancamento": numero})
    session.commit()
    return {"criados": criados, "valor_por_pessoa": valor, "total": round(valor * len(criados), 2)}


# ---------------------------------------------------------------------------
# Retirada
# ---------------------------------------------------------------------------
class RetiradaIn(BaseModel):
    valor: float
    data: date
    forma_pagamento: str
    conta_bancaria: str | None = None
    numero_documento_pagamento: str | None = None
    motivo: str | None = None


@router.post("/{pessoa_id}/retiradas")
def registrar_retirada(
    pessoa_id: int, dados: RetiradaIn, session: Session = Depends(get_session), user=Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    pessoa = _pessoa_ou_404(session, pessoa_id, fazenda_id)
    if dados.forma_pagamento not in FORMAS_RETIRADA:
        raise HTTPException(status_code=400, detail="Forma de pagamento inválida")
    valor = round(dados.valor, 2)
    if valor <= 0:
        raise HTTPException(status_code=400, detail="Informe um valor maior que zero")
    movs = _movimentos_da_pessoa(session, pessoa_id, fazenda_id)
    saldo_antes = _saldo(movs)
    if valor > saldo_antes:
        raise HTTPException(
            status_code=409,
            detail=f"Valor acima do saldo de R$ {_brl(saldo_antes)}. Para adiantar, use o Vale.",
        )
    mov = CaixaMovimento(
        fazenda_id=fazenda_id, pessoa_id=pessoa_id, tipo="retirada", valor=-valor, data=dados.data,
        motivo=(dados.motivo or "Retirada do caixa").strip() or "Retirada do caixa",
        forma_pagamento=dados.forma_pagamento, conta_bancaria=dados.conta_bancaria or None,
        numero_documento_pagamento=(dados.numero_documento_pagamento or "").strip() or None,
        usuario_id=usuario_id_seguro(user),
    )
    session.add(mov)
    session.flush()
    mov.numero_recibo = f"CX-{dados.data.year}-{mov.id:05d}"
    session.add(mov)
    session.commit()
    session.refresh(mov)
    return {"movimento": mov.model_dump(), "pessoa": {"id": pessoa.id, "nome": pessoa.nome, "tipo": pessoa.tipo},
            "saldo_anterior": saldo_antes, "saldo_depois": round(saldo_antes - valor, 2)}


class ComprovanteIn(BaseModel):
    numero_documento_pagamento: str | None = None
    anexo_id: int | None = None


@router.put("/{pessoa_id}/movimentos/{movimento_id}/comprovante")
def registrar_comprovante_da_retirada(
    pessoa_id: int, movimento_id: int, dados: ComprovanteIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """Anexa (ou troca) o comprovante de uma retirada — inclusive a do pagamento direto do rateio, mesmo
    depois de confirmada: o nº do comprovante e/ou o arquivo (PessoaAnexo da própria pessoa)."""
    from fazenda.models import PessoaAnexo

    _pessoa_ou_404(session, pessoa_id, fazenda_id)
    mov = _movimento_ou_404(session, pessoa_id, movimento_id, fazenda_id)
    if mov.tipo != "retirada":
        raise HTTPException(status_code=400, detail="Só retirada tem comprovante")
    if dados.anexo_id is not None:
        a = session.get(PessoaAnexo, dados.anexo_id)
        if not a or a.pessoa_id != pessoa_id or a.fazenda_id != fazenda_id:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado nesta pessoa")
        mov.comprovante_anexo_id = a.id
    if dados.numero_documento_pagamento is not None:
        mov.numero_documento_pagamento = dados.numero_documento_pagamento.strip() or None
    session.add(mov)
    session.commit()
    session.refresh(mov)
    return {"movimento": mov.model_dump()}


@router.get("/{pessoa_id}/movimentos/{movimento_id}/recibo")
def recibo_movimento(
    pessoa_id: int, movimento_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id), _: object = Depends(exigir_admin),
) -> dict:
    """Dados do recibo de uma retirada (saldo antes/depois calculados na data do movimento)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pessoa = _pessoa_ou_404(session, pessoa_id, fazenda_id)
    mov = _movimento_ou_404(session, pessoa_id, movimento_id, fazenda_id)
    if mov.tipo != "retirada":
        raise HTTPException(status_code=400, detail="Só retirada tem recibo")
    movs = _movimentos_da_pessoa(session, pessoa_id, fazenda_id)
    antes = round(sum(m.valor for m in movs if (m.data, m.id) < (mov.data, mov.id)), 2)
    return {
        "movimento": mov.model_dump(), "pessoa": {"id": pessoa.id, "nome": pessoa.nome, "tipo": pessoa.tipo},
        "saldo_anterior": antes, "saldo_depois": round(antes + mov.valor, 2),
    }


# ---------------------------------------------------------------------------
# Correção: estorno e exclusão
# ---------------------------------------------------------------------------
class EstornoIn(BaseModel):
    motivo: str


@router.post("/{pessoa_id}/movimentos/{movimento_id}/estornar")
def estornar_movimento(
    pessoa_id: int, movimento_id: int, dados: EstornoIn, session: Session = Depends(get_session),
    user=Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """Cria o movimento contrário, com a data de HOJE. O original continua visível."""
    _pessoa_ou_404(session, pessoa_id, fazenda_id)
    original = _movimento_ou_404(session, pessoa_id, movimento_id, fazenda_id)
    motivo = (dados.motivo or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo do estorno")
    if original.tipo == "retencao" and original.folha_id:
        raise HTTPException(
            status_code=409,
            detail="Esta retenção veio de uma folha paga. Para desfazê-la, estorne o pagamento da folha em Fechamento da folha.",
        )
    if original.tipo == "rateio" and original.rateio_id:
        raise HTTPException(
            status_code=409,
            detail="Este crédito veio de um rateio do PL. Para desfazê-lo, use 'Desfazer rateio' no caixa do time.",
        )
    novo = regras.estornar_movimento(session, original, motivo, usuario_id_seguro(user), fazenda_id)
    session.commit()
    session.refresh(novo)
    return {"estorno": novo.model_dump()}


@router.delete("/{pessoa_id}/movimentos/{movimento_id}")
def excluir_movimento(
    pessoa_id: int, movimento_id: int, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: object = Depends(exigir_admin),
) -> dict:
    """Só o ÚLTIMO movimento da pessoa, que não seja estorno nem tenha sido estornado."""
    _pessoa_ou_404(session, pessoa_id, fazenda_id)
    mov = _movimento_ou_404(session, pessoa_id, movimento_id, fazenda_id)
    movs = _movimentos_da_pessoa(session, pessoa_id, fazenda_id)
    if mov.tipo == "estorno":
        raise HTTPException(status_code=409, detail="Estorno não se exclui: ele é o rastro da correção")
    if mov.tipo == "retencao" and mov.folha_id:
        raise HTTPException(status_code=409, detail="Retenção de folha não se exclui: estorne o pagamento da folha.")
    if mov.tipo == "rateio" and mov.rateio_id:
        raise HTTPException(status_code=409, detail="Crédito de rateio não se exclui: desfaça o rateio no caixa do time.")
    if any(m.estorna_id == mov.id for m in movs):
        raise HTTPException(status_code=409, detail="Este movimento já foi estornado e não pode ser excluído")
    if mov.id != max(m.id for m in movs):
        raise HTTPException(
            status_code=409,
            detail="Só o último movimento pode ser excluído. Há movimentos depois dele: use o estorno.",
        )
    lancamento_id = mov.lancamento_id
    session.delete(mov)
    session.flush()
    if lancamento_id:
        conta = session.get(ContaGerencial, lancamento_id)
        if conta is not None and conta.tipo_documento == TIPO_DOC_ENTRADA:
            session.delete(conta)
    session.commit()
    return {"excluido": True, "movimento_id": movimento_id}
