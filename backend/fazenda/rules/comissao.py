"""
Comissão de corretagem — gerada a partir de uma venda ou compra de animal.

Sempre cria uma despesa (ContaGerencial) separada e visível, nunca abatida
silenciosamente do valor bruto da venda/compra (mesma filosofia de manter
desconto/acréscimo sempre à parte, nunca líquido escondido). A diferença
entre as duas formas está apenas no estado de liquidação dessa despesa:
  - "redirecionado": liquidada junto com a transação (já paga, mesma data).
  - "separado": conta a pagar em aberto, liquidada depois normalmente.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session

from fazenda.models import ComissaoCorretagem, ContaGerencial
from fazenda.api.routers.financeiro import _proximo_numero_lancamento

FORMAS_COMISSAO = ("redirecionado", "separado")


def criar_comissao(
    session: Session,
    *,
    origem_tipo: str,
    numero_lancamento_origem: str,
    corretor_nome: str,
    valor_comissao: float,
    forma: str,
    data_transacao: date,
    descricao_origem: str,
) -> ComissaoCorretagem:
    """Cria a despesa de comissão (ContaGerencial) e o registro de acompanhamento."""
    numero_lancamento_comissao = _proximo_numero_lancamento(session, data_transacao.year)

    conta = ContaGerencial(
        numero_lancamento=numero_lancamento_comissao,
        descricao=f"Comissão de corretagem — {corretor_nome} ({descricao_origem})",
        data_vencimento=data_transacao,
        data_competencia=data_transacao,
        fornecedor_cliente=corretor_nome,
        tipo_documento="Comissão de corretagem",
        valor_total=round(valor_comissao, 2),
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
    )
    if forma == "redirecionado":
        conta.data_pagamento = data_transacao
        conta.valor_pago = round(valor_comissao, 2)
    session.add(conta)

    comissao = ComissaoCorretagem(
        origem_tipo=origem_tipo,
        numero_lancamento=numero_lancamento_origem,
        corretor_nome=corretor_nome,
        valor_comissao=round(valor_comissao, 2),
        forma=forma,
        numero_lancamento_comissao=numero_lancamento_comissao,
    )
    session.add(comissao)
    return comissao
