"""
Comissão de corretagem — gerada a partir de uma venda ou compra de animal.

Sempre cria uma despesa (ContaGerencial) separada e visível, nunca abatida
silenciosamente do valor bruto da venda/compra (mesma filosofia de manter
desconto/acréscimo sempre à parte, nunca líquido escondido). A diferença
entre as duas formas está no estado de liquidação dessa despesa:
  - "redirecionado": a comissão é liquidada JUNTO da transação de origem —
    copia o estado de pagamento real dela (se a compra/venda está paga hoje,
    a comissão também está; se a compra/venda é uma conta a pagar futura, a
    comissão TAMBÉM fica em aberto, com o mesmo vencimento — nunca marcada
    como paga "de brincadeira" só porque a forma escolhida foi essa).
  - "separado": conta a pagar própria e independente da transação de origem,
    com seu próprio vencimento/parcelamento, liquidada depois normalmente.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from fazenda.models import ComissaoCorretagem, ContaGerencial, PlanoContaGerencial
from fazenda.api.routers.financeiro import _proximo_numero_lancamento

FORMAS_COMISSAO = ("redirecionado", "separado")

CODIGO_CORRETAGEM_PADRAO = "3.99.99"


def garantir_conta_corretagem(session: Session) -> str:
    """Acha a conta gerencial de "corretagem" já cadastrada (por nome) ou cria
    uma, quando a fazenda ainda não tem uma — nunca deixa a despesa de
    comissão sem conta gerencial vinculada."""
    existente = session.exec(
        select(PlanoContaGerencial).where(PlanoContaGerencial.nome.ilike("%corretagem%"))
    ).first()
    if existente:
        return existente.codigo
    if session.get(PlanoContaGerencial, CODIGO_CORRETAGEM_PADRAO):
        return CODIGO_CORRETAGEM_PADRAO
    if not session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.codigo == CODIGO_CORRETAGEM_PADRAO)).first():
        session.add(PlanoContaGerencial(
            codigo=CODIGO_CORRETAGEM_PADRAO, nome="Comissão de corretagem", ativa=True, natureza="servico",
        ))
        session.commit()
    return CODIGO_CORRETAGEM_PADRAO


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
    centro_custo: str | None = None,
    # Estado de pagamento REAL da transação de origem (compra/venda do animal)
    # — só usado quando forma="redirecionado", para a comissão copiar fielmente
    # se/quando ela foi (ou será) paga, em vez de assumir que já foi.
    origem_paga: bool = False,
    origem_data_pagamento: date | None = None,
    origem_conta_bancaria: str | None = None,
    # "separado": vencimento e parcelamento próprios da comissão.
    data_vencimento_comissao: date | None = None,
    parcelas_comissao: list[tuple[date, float]] | None = None,
    fazenda_id: int | None = None,
) -> ComissaoCorretagem:
    """Cria a(s) despesa(s) de comissão (ContaGerencial) e o registro de acompanhamento."""
    numero_lancamento_comissao = _proximo_numero_lancamento(session, data_transacao.year)
    codigo_conta = garantir_conta_corretagem(session)

    campos_comuns = dict(
        numero_lancamento=numero_lancamento_comissao,
        codigo_conta=codigo_conta,
        descricao=f"Comissão de corretagem — {corretor_nome} ({descricao_origem})",
        data_competencia=data_transacao,
        centro_custo=centro_custo,
        fornecedor_cliente=corretor_nome,
        tipo_documento="Comissão de corretagem",
        tipo="despesa", origem="auto",
        fazenda_id=fazenda_id,
    )

    if forma == "redirecionado":
        conta = ContaGerencial(
            **campos_comuns,
            data_vencimento=origem_data_pagamento or data_transacao,
            valor_total=round(valor_comissao, 2),
            parcela_num=1, parcela_total=1,
        )
        if origem_paga:
            conta.data_pagamento = origem_data_pagamento or data_transacao
            conta.valor_pago = round(valor_comissao, 2)
            conta.conta_bancaria = origem_conta_bancaria
        session.add(conta)
    elif parcelas_comissao:
        total = len(parcelas_comissao)
        for i, (venc, valor) in enumerate(parcelas_comissao, start=1):
            session.add(ContaGerencial(
                **campos_comuns, data_vencimento=venc, valor_total=round(valor, 2),
                parcela_num=i, parcela_total=total,
            ))
    else:
        session.add(ContaGerencial(
            **campos_comuns,
            data_vencimento=data_vencimento_comissao or data_transacao,
            valor_total=round(valor_comissao, 2),
            parcela_num=1, parcela_total=1,
        ))

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
