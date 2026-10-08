"""
Retirada do caixa do funcionário pelo BANCO entra no saldo — Fase A, PR 6
(achado da auditoria: a retirada gravava só o `CaixaMovimento` com a conta
bancária, sem lançamento nenhum, e o dinheiro que saía do banco não baixava o
saldo nem aparecia no Fluxo).

Com a flag `financeiro_regras_v2`, a retirada paga por transferência/pix/débito
de uma conta corrente gera uma `ContaGerencial` DESPESA já baixada:

  - natureza OBRIGACAO: quita o que a fazenda já devia ao funcionário (o custo
    foi reconhecido quando o dinheiro ENTROU no caixa) — fica fora da DRE e dos
    custos, entra no saldo, no Caixa Real e no Fluxo;
  - `gerado_por = "caixa_retirada"`, ligada ao movimento pelo
    `numero_lancamento` (não pelo `lancamento_id` do movimento, que o estorno
    genérico do caixa usa para devolver despesa de pessoal);
  - estorno da retirada = lançamento contrário (receita OBRIGACAO, mesma conta,
    na data do estorno); exclusão da retirada apaga o lançamento junto.

Retirada em dinheiro (ou sem conta bancária) não mexe em banco: nada é criado.
"""
from __future__ import annotations

from sqlmodel import Session, select

from fazenda.models import ContaGerencial
from fazenda.rules.natureza import OBRIGACAO
from fazenda.rules.saldo_conta import GERADO_POR_RETIRADA_CAIXA

TIPO_DOC_RETIRADA = "Retirada do caixa do funcionário"
TIPO_DOC_ESTORNO_RETIRADA = "Estorno de retirada do caixa"


def retirada_mexe_no_banco(mov) -> bool:
    return bool(getattr(mov, "conta_bancaria", None)) and (getattr(mov, "forma_pagamento", None) or "") != "dinheiro"


def _nota(session: Session, mov, *, tipo: str, data, descricao: str, fornecedor: str | None, tipo_documento: str,
          conta_bancaria: str | None, conta_corrente_id: int | None, valor: float) -> ContaGerencial:
    from fazenda.api.routers.financeiro import _proximo_numero_lancamento

    numero = _proximo_numero_lancamento(session, data.year)
    conta = ContaGerencial(
        numero_lancamento=numero, descricao=descricao[:500], fornecedor_cliente=fornecedor,
        data_emissao=data, data_vencimento=data, data_competencia=data,
        tipo_documento=tipo_documento, centro_custo="Pecuária Leiteira",
        valor_total=valor, parcela_num=1, parcela_total=1, tipo=tipo, origem="auto",
        data_pagamento=data, valor_pago=valor, desconto_acrescimo=0.0,
        conta_bancaria=conta_bancaria, conta_corrente_id=conta_corrente_id,
        forma_pagamento=getattr(mov, "forma_pagamento", None), numero_documento_pagamento=getattr(mov, "numero_documento_pagamento", None),
        natureza_fin=OBRIGACAO, gerado_por=GERADO_POR_RETIRADA_CAIXA, fazenda_id=mov.fazenda_id,
    )
    session.add(conta)
    session.flush()
    return conta


def lancar_retirada_no_banco(session: Session, mov, nome_pessoa: str | None) -> ContaGerencial | None:
    """Cria a saída bancária da retirada `mov` (já com id). Não commita."""
    if not retirada_mexe_no_banco(mov):
        return None
    from fazenda.api.routers.financeiro import resolver_conta_corrente_id

    conta = _nota(
        session, mov, tipo="despesa", data=mov.data,
        descricao=f"Retirada do caixa · {nome_pessoa or '—'} · {mov.numero_recibo or mov.id}", fornecedor=nome_pessoa,
        tipo_documento=TIPO_DOC_RETIRADA, conta_bancaria=mov.conta_bancaria,
        conta_corrente_id=resolver_conta_corrente_id(session, mov.fazenda_id, mov.conta_bancaria),
        valor=round(abs(mov.valor), 2),
    )
    mov.numero_lancamento = conta.numero_lancamento
    session.add(mov)
    return conta


def nota_da_retirada(session: Session, mov) -> ContaGerencial | None:
    if not getattr(mov, "numero_lancamento", None):
        return None
    query = select(ContaGerencial).where(
        ContaGerencial.numero_lancamento == mov.numero_lancamento,
        ContaGerencial.gerado_por == GERADO_POR_RETIRADA_CAIXA,
        ContaGerencial.tipo_documento == TIPO_DOC_RETIRADA,
    )
    if mov.fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == mov.fazenda_id)
    return session.exec(query).first()


def estornar_retirada_no_banco(session: Session, original, estorno) -> ContaGerencial | None:
    """O dinheiro volta para a conta na data do estorno (receita OBRIGACAO). Não commita."""
    nota = nota_da_retirada(session, original)
    if nota is None:
        return None
    contra = _nota(
        session, original, tipo="receita", data=estorno.data,
        descricao=f"Estorno de retirada · {nota.fornecedor_cliente or '—'} · {nota.numero_lancamento}",
        fornecedor=nota.fornecedor_cliente, tipo_documento=TIPO_DOC_ESTORNO_RETIRADA, conta_bancaria=nota.conta_bancaria,
        conta_corrente_id=nota.conta_corrente_id, valor=nota.valor_total or 0.0,
    )
    estorno.numero_lancamento = contra.numero_lancamento
    session.add(estorno)
    return contra


def excluir_retirada_no_banco(session: Session, mov) -> None:
    nota = nota_da_retirada(session, mov)
    if nota is not None:
        session.delete(nota)
