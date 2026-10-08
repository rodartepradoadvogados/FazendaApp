"""
Backfill do cartão por item (Fase A, PR 5) — PLANO e APLICAÇÃO separados. Quem
chama é o comando `python -m scripts.backfill_cartao_por_item` (dry-run por
padrão; grava só com `--aplicar`, num lote do `migracao_log_financeiro`; desfaz
com `--reverter LOTE`, que apaga as notas criadas).

Para cada compra no cartão (`LancamentoCartao`) ainda sem nota:

  - fatura ABERTA ou FECHADA: cria a nota em aberto (competência = data da
    compra, vencimento = o da fatura, `gerado_por="backfill_cartao_aberta"`) —
    igual à que a compra ganharia hoje com a flag ligada; vai ser paga pela fatura;
  - fatura PAGA pela nota genérica "Fatura X" (`fatura.numero_lancamento`): cria
    a nota da compra JÁ PAGA na data da genérica, mas SEM conta bancária e com
    `gerado_por="backfill_cartao"` — ela só classifica a DRE (conta e
    competência da compra); o dinheiro continua contado UMA vez, pela genérica,
    que passa a natureza OBRIGACAO (fora da DRE, continua no saldo, no extrato
    e no Livro). Saldo, Caixa Real e Fluxo não mudam;
  - o resto vai para a LISTA DE REVISÃO: fatura paga sem a nota genérica, nota
    genérica com natureza já escolhida à mão (não sobrescrevo), soma das compras
    diferente do total da genérica.

Exige a flag `financeiro_regras_v2` ligada na fazenda: sem ela, as notas novas
apareceriam nos relatórios antigos ao lado da genérica (contaria em dobro).
Nunca toca `valor_total`/`valor_pago` de linha existente.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from fazenda.rules.natureza import OBRIGACAO
from fazenda.rules.saldo_conta import GERADO_POR_BACKFILL_CARTAO, GERADO_POR_BACKFILL_CARTAO_ABERTA

MIGRACAO = "backfill_cartao_por_item_v1"


@dataclass
class PlanoCartao:
    fazenda_id: int
    # {tipo: "nota_aberta"|"nota_paga", compra_id, fatura_id, competencia, descricao, valor, data_compra, generica_id}
    notas: list[dict] = field(default_factory=list)
    # {conta_id, numero_lancamento, fatura_id, valor}
    genericas: list[dict] = field(default_factory=list)
    # {fatura_id, competencia, motivo, valor}
    revisao: list[dict] = field(default_factory=list)


def _generica(session: Session, fazenda_id: int, numero: str | None):
    from fazenda.models import ContaGerencial

    if not numero:
        return []
    return list(session.exec(select(ContaGerencial).where(
        ContaGerencial.fazenda_id == fazenda_id, ContaGerencial.numero_lancamento == numero,
    )).all())


def planejar(session: Session, fazenda_id: int) -> PlanoCartao:
    from fazenda.models import FaturaCartao, LancamentoCartao

    plano = PlanoCartao(fazenda_id=fazenda_id)
    faturas = session.exec(
        select(FaturaCartao).where(FaturaCartao.fazenda_id == fazenda_id).order_by(FaturaCartao.id)
    ).all()
    for fatura in faturas:
        compras = [c for c in session.exec(
            select(LancamentoCartao).where(LancamentoCartao.fatura_id == fatura.id).order_by(LancamentoCartao.id)
        ).all() if not c.numero_lancamento]
        if not compras:
            continue
        base = {"fatura_id": fatura.id, "competencia": fatura.competencia}
        if fatura.status != "paga":
            for c in compras:
                plano.notas.append({**base, "tipo": "nota_aberta", "compra_id": c.id, "descricao": c.descricao,
                                    "valor": c.valor, "data_compra": c.data_compra.isoformat(), "generica_id": None})
            continue
        genericas = _generica(session, fazenda_id, fatura.numero_lancamento)
        total_compras = round(sum(c.valor for c in compras), 2)
        if len(genericas) != 1 or genericas[0].data_pagamento is None:
            plano.revisao.append({**base, "valor": total_compras,
                                  "motivo": "fatura paga sem a nota genérica de pagamento (ou com mais de uma parcela)"})
            continue
        generica = genericas[0]
        if generica.natureza_fin not in (None, OBRIGACAO):
            plano.revisao.append({**base, "valor": total_compras, "motivo": (
                f"a nota {generica.numero_lancamento} já tem natureza {generica.natureza_fin} escolhida à mão")})
            continue
        if round(total_compras - (generica.valor_total or 0), 2) != 0:
            plano.revisao.append({**base, "valor": total_compras, "motivo": (
                f"as compras somam R$ {total_compras:.2f} e a nota {generica.numero_lancamento} R$ {generica.valor_total:.2f}")})
            continue
        for c in compras:
            plano.notas.append({**base, "tipo": "nota_paga", "compra_id": c.id, "descricao": c.descricao,
                                "valor": c.valor, "data_compra": c.data_compra.isoformat(), "generica_id": generica.id})
        if generica.natureza_fin is None:
            plano.genericas.append({**base, "conta_id": generica.id, "numero_lancamento": generica.numero_lancamento,
                                    "valor": generica.valor_total})
    return plano


def aplicar(session: Session, plano: PlanoCartao, lote: str) -> dict:
    """Cria as notas e marca as genéricas, com log. Não commita."""
    from fazenda.models import CartaoCredito, ContaGerencial, FaturaCartao, LancamentoCartao, LancamentoItem
    from fazenda.rules import cartao_por_item
    from fazenda.rules.migracao_log import registrar_criacao, registrar_mudanca

    criadas = 0
    for acao in plano.notas:
        compra = session.get(LancamentoCartao, acao["compra_id"])
        if compra is None or compra.numero_lancamento or compra.fazenda_id != plano.fazenda_id:
            continue
        fatura = session.get(FaturaCartao, compra.fatura_id)
        cartao = session.get(CartaoCredito, compra.cartao_id)
        paga = acao["tipo"] == "nota_paga"
        nota = cartao_por_item.nova_nota_da_compra(
            session, cartao, fatura, compra, usuario_id=compra.usuario_id,
            gerado_por=GERADO_POR_BACKFILL_CARTAO if paga else GERADO_POR_BACKFILL_CARTAO_ABERTA,
        )
        if paga:
            generica = session.get(ContaGerencial, acao["generica_id"])
            # Já paga, na data da genérica, SEM conta bancária: só classifica a
            # DRE — o dinheiro está na genérica (saldo e Fluxo não mudam).
            nota.data_pagamento = generica.data_pagamento
            nota.valor_pago = nota.valor_total
            nota.desconto_acrescimo = 0.0
            nota.forma_pagamento = generica.forma_pagamento
            session.add(nota)
            session.flush()
        motivo = f"compra no cartão (fatura {fatura.competencia}{', paga pela nota ' + str(acao['generica_id']) if paga else ''})"
        registrar_criacao(session, fazenda_id=plano.fazenda_id, lote=lote, migracao=MIGRACAO,
                          tabela="conta_gerencial", registro=nota, motivo=motivo)
        item = session.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == nota.numero_lancamento,
                                                         LancamentoItem.fazenda_id == plano.fazenda_id)).one()
        registrar_criacao(session, fazenda_id=plano.fazenda_id, lote=lote, migracao=MIGRACAO,
                          tabela="lancamento_item", registro=item, motivo=motivo)
        numero = compra.numero_lancamento
        compra.numero_lancamento = None  # registrar_mudanca grava o antes (None) e o depois
        registrar_mudanca(session, fazenda_id=plano.fazenda_id, lote=lote, migracao=MIGRACAO,
                          tabela="lancamento_cartao", registro=compra, campo="numero_lancamento",
                          valor_depois=numero, motivo="nota da compra")
        criadas += 1
    marcadas = 0
    for g in plano.genericas:
        generica = session.get(ContaGerencial, g["conta_id"])
        if generica is None or generica.natureza_fin is not None or generica.fazenda_id != plano.fazenda_id:
            continue
        registrar_mudanca(session, fazenda_id=plano.fazenda_id, lote=lote, migracao=MIGRACAO,
                          tabela="conta_gerencial", registro=generica, campo="natureza_fin", valor_depois=OBRIGACAO,
                          motivo="nota genérica de fatura de cartão: as compras passam a ter nota própria")
        marcadas += 1
    session.flush()
    return {"notas_criadas": criadas, "genericas_marcadas": marcadas}
