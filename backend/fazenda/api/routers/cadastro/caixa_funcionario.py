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

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import CaixaMovimento, ContaGerencial, Pessoa
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

# Tipo de pessoa (CSV em Pessoa.tipo) → grupo mostrado nos filtros da tela.
_GRUPO_POR_TIPO = {
    "funcionário": "clt", "funcionario": "clt",
    "empreiteiro": "empreita",
    "prestador de serviços": "contrato", "prestador de servicos": "contrato",
    "diarista": "diaria",
}


def _grupos_da_pessoa(pessoa: Pessoa) -> list[str]:
    grupos: list[str] = []
    for parte in (pessoa.tipo or "").split(","):
        g = _GRUPO_POR_TIPO.get(parte.strip().lower())
        if g and g not in grupos:
            grupos.append(g)
    return grupos


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
    if original.tipo == "estorno":
        raise HTTPException(status_code=409, detail="Um estorno não pode ser estornado")
    movs = _movimentos_da_pessoa(session, pessoa_id, fazenda_id)
    if any(m.estorna_id == original.id for m in movs):
        raise HTTPException(status_code=409, detail="Este movimento já foi estornado")
    # Estornar uma ENTRADA tira dinheiro do caixa: não pode deixar o saldo negativo.
    if original.valor > 0 and _saldo(movs) - original.valor < 0:
        raise HTTPException(
            status_code=409,
            detail="O saldo desta entrada já foi usado em retirada(s). Estorne a retirada primeiro.",
        )
    hoje = date.today()
    novo = CaixaMovimento(
        fazenda_id=fazenda_id, pessoa_id=pessoa_id, tipo="estorno", valor=-original.valor, data=hoje,
        motivo=f"Estorno de {original.numero_lancamento or original.numero_recibo or f'#{original.id}'}: {motivo}",
        estorna_id=original.id, usuario_id=usuario_id_seguro(user),
    )
    # Entrada da fazenda: o Financeiro recebe o lançamento contrário (receita), para o gasto não ficar de pé.
    if original.lancamento_id:
        conta_original = session.get(ContaGerencial, original.lancamento_id)
        if conta_original is not None:
            numero = _proximo_numero_lancamento(session, hoje.year)
            contra = ContaGerencial(
                numero_lancamento=numero,
                descricao=f"Estorno de {conta_original.numero_lancamento} · {conta_original.fornecedor_cliente or ''} · {motivo}"[:500],
                data_vencimento=hoje, data_competencia=hoje.replace(day=1),
                fornecedor_cliente=conta_original.fornecedor_cliente, tipo_documento=TIPO_DOC_ESTORNO,
                centro_custo=conta_original.centro_custo, valor_total=conta_original.valor_total,
                parcela_num=1, parcela_total=1, tipo="receita", origem="auto",
                data_pagamento=hoje, valor_pago=conta_original.valor_total,
                conta_bancaria=conta_original.conta_bancaria, forma_pagamento="caixa_funcionario",
                fazenda_id=fazenda_id,
            )
            session.add(contra)
            session.flush()
            novo.lancamento_id = contra.id
            novo.numero_lancamento = numero
    session.add(novo)
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
