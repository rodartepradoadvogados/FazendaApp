"""
Cartão de crédito por item — Fase A, PR 5 (P0-3 da auditoria; ver
docs/financeiro-regras-v2.md §10). Só vale com a flag `financeiro_regras_v2`.

Antes: a compra no cartão era só um `LancamentoCartao` (nenhum relatório lia a
conta e o centro dela) e, ao pagar a fatura, nascia UMA nota genérica "Fatura X"
sem conta, com competência na data do PAGAMENTO — a ração comprada no cartão em
março caía em "não classificado" em abril, e a fatura aberta não aparecia em
Contas a pagar nem no Caixa Real.

Agora (decisões do dono):

  - UMA nota (`ContaGerencial` + `LancamentoItem`) por compra, na hora da compra:
    competência = data da compra, vencimento = o da fatura, conta e centro da
    compra, `fatura_cartao_id` = a fatura. IOF e anuidade são compras próprias
    (lançadas como compra, numa conta própria) — o rateio de diferença fica só
    para o que não se identifica;
  - a nota em aberto entra em Contas a pagar (o total sobe: decisão a) e no
    Caixa Real, no vencimento da fatura;
  - ela só se paga PELA FATURA: a baixa individual, o lote e o lote detalhado
    recusam 409 (`_recusar_se_em_fatura`). Pagar a fatura baixa todas as notas
    de uma vez (mesma data, conta e forma) e, se o pago difere do total, rateia
    a diferença em centavos, proporcional ao valor de cada nota, a sobra na
    última — o mesmo de `faturas_fornecedor.pagar_parcela`; a diferença vai
    para `desconto_acrescimo` de cada nota (juros/desconto em Outras, PR 7);
  - a nota genérica "Fatura X" deixa de ser criada.
"""
from __future__ import annotations

from sqlmodel import Session, select

from fazenda.models import CartaoCredito, ContaGerencial, FaturaCartao, LancamentoCartao, LancamentoItem

TIPO_DOCUMENTO_COMPRA_CARTAO = "Compra no cartão"


def ratear_diferenca(valores: list[float], pago: float) -> list[float]:
    """Cota da diferença (pago − Σ valores) de cada nota, em reais, rateada em
    centavos proporcionalmente ao valor; a sobra do arredondamento fica na
    última. Ex.: [800, 300] pagos por 1.111 → [8.0, 3.0]."""
    if not valores:
        return []
    soma = round(sum(valores), 2)
    dif_c = round((pago - soma) * 100)
    cents = [round(v * 100) for v in valores]
    total_c = sum(cents)
    if not total_c:
        cotas = [0] * len(valores)
    else:
        cotas = [dif_c * v // total_c if dif_c >= 0 else -((-dif_c) * v // total_c) for v in cents]
    cotas[-1] += dif_c - sum(cotas)
    return [round(c / 100, 2) for c in cotas]


def nova_nota_da_compra(
    session: Session, cartao: CartaoCredito, fatura: FaturaCartao, compra: LancamentoCartao, *,
    usuario_id: int | None = None, gerado_por: str | None = None,
) -> ContaGerencial:
    """Cria a nota (e o item) de uma compra e liga `compra.numero_lancamento`.
    Não commita (quem chama decide a transação)."""
    from fazenda.api.routers.financeiro import _proximo_numero_lancamento
    from fazenda.rules.centro_custo import mapear_centro_custo

    numero = _proximo_numero_lancamento(session, compra.data_compra.year)
    centro = mapear_centro_custo(compra.centro_custo) if compra.centro_custo else None
    parcela = f" ({compra.parcela_num}/{compra.parcela_total})" if compra.parcela_num and compra.parcela_total else ""
    descricao = f"{compra.descricao}{parcela}"[:500]
    nota = ContaGerencial(
        fazenda_id=cartao.fazenda_id, numero_lancamento=numero,
        codigo_conta=compra.codigo_conta_gerencial, descricao=descricao,
        fornecedor_cliente=cartao.banco_emissor or cartao.apelido,
        tipo_documento=TIPO_DOCUMENTO_COMPRA_CARTAO, numero_nota=f"Cartão {cartao.apelido} · {fatura.competencia}",
        data_emissao=compra.data_compra, data_competencia=compra.data_compra,
        data_vencimento=fatura.data_vencimento,
        valor_total=round(compra.valor, 2), parcela_num=1, parcela_total=1,
        centro_custo=centro or "Pecuária Leiteira", tipo="despesa", origem="cartao",
        fatura_cartao_id=fatura.id, gerado_por=gerado_por, usuario_id=usuario_id,
    )
    item = LancamentoItem(
        fazenda_id=cartao.fazenda_id, numero_lancamento=numero, tipo="despesa",
        data_competencia=compra.data_compra,
        codigo_conta_gerencial=compra.codigo_conta_gerencial, nome_conta_gerencial=compra.nome_conta_gerencial,
        centro_custo=centro, produto=compra.descricao[:500], tipo_item="servico", descricao=compra.observacao,
        valor_total=round(compra.valor, 2),
    )
    session.add(nota)
    session.add(item)
    session.flush()
    compra.numero_lancamento = numero
    session.add(compra)
    return nota


def compras_da_fatura(session: Session, fatura: FaturaCartao) -> list[LancamentoCartao]:
    return list(session.exec(
        select(LancamentoCartao).where(LancamentoCartao.fatura_id == fatura.id).order_by(LancamentoCartao.id)
    ).all())


def notas_da_fatura(session: Session, fatura: FaturaCartao) -> list[ContaGerencial]:
    query = select(ContaGerencial).where(ContaGerencial.fatura_cartao_id == fatura.id).order_by(ContaGerencial.id)
    if fatura.fazenda_id is not None:
        query = query.where(ContaGerencial.fazenda_id == fatura.fazenda_id)
    return list(session.exec(query).all())


def garantir_notas(session: Session, cartao: CartaoCredito, fatura: FaturaCartao, usuario_id: int | None = None) -> list[ContaGerencial]:
    """Compra lançada antes da flag (sem nota) ganha a nota agora — a fatura
    nunca é paga deixando uma compra sem baixa. Não commita."""
    for compra in compras_da_fatura(session, fatura):
        if not compra.numero_lancamento:
            nova_nota_da_compra(session, cartao, fatura, compra, usuario_id=usuario_id)
    return notas_da_fatura(session, fatura)
