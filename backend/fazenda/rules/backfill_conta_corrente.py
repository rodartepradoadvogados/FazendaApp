"""
Backfill do vínculo `conta_gerencial.conta_corrente_id` (Fase A, PR 6) — PLANO e
APLICAÇÃO separados. Quem chama é o comando
`python -m scripts.backfill_conta_corrente` (dry-run por padrão; grava só com
`--aplicar`, num lote do `migracao_log_financeiro`; desfaz com `--reverter LOTE`).

Até aqui o pagamento só sabia de que conta saiu pelo TEXTO livre
`conta_bancaria` ("Banco · Agência · Conta"); o saldo casava a string exata e
qualquer diferença de digitação ("Banco do Brasil", "Sicredi") sumia do saldo.
Regras de casamento, na ordem (`rules/saldo_conta.casar_conta_corrente`):

  1. exato — o texto é o rótulo de uma conta da fazenda;
  2. normalizado — banco + dígitos da agência e da conta aparecem no texto
     (sem acento, espaço e pontuação);
  3. banco único — o texto é só o nome do banco e a fazenda tem uma conta nele.

O que sobra (ambíguo ou sem conta parecida) vai para a LISTA DE REVISÃO — a
tela/rota "Lançamentos sem conta bancária identificada" liga em lote
(`PUT /financeiro/lancamentos/conta-corrente-lote`). Nunca toca
`valor_total`/`valor_pago`; nunca sobrescreve um vínculo já gravado.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from fazenda.rules.saldo_conta import ContaRef, casar_conta_corrente

MIGRACAO = "backfill_conta_corrente_v1"


@dataclass
class PlanoContaCorrente:
    fazenda_id: int
    # {id, numero_lancamento, conta_bancaria, para, regra, valor, data_pagamento}
    mudancas: list[dict] = field(default_factory=list)
    # {id, numero_lancamento, conta_bancaria, motivo, valor, data_pagamento}
    revisao: list[dict] = field(default_factory=list)


def _refs(session: Session, fazenda_id: int) -> list[ContaRef]:
    from fazenda.api.routers.financeiro import rotulo_conta_corrente
    from fazenda.models import ContaCorrente

    contas = session.exec(select(ContaCorrente).where(ContaCorrente.fazenda_id == fazenda_id)).all()
    return [ContaRef(c.id, c.banco, c.agencia, c.numero_conta, rotulo_conta_corrente(c)) for c in contas]


def planejar(session: Session, fazenda_id: int) -> PlanoContaCorrente:
    from fazenda.models import ContaGerencial

    plano = PlanoContaCorrente(fazenda_id=fazenda_id)
    refs = _refs(session, fazenda_id)
    query = select(ContaGerencial).where(
        ContaGerencial.fazenda_id == fazenda_id,
        ContaGerencial.conta_corrente_id == None,  # noqa: E711
        ContaGerencial.conta_bancaria != None,  # noqa: E711
        ContaGerencial.conta_bancaria != "",
    ).order_by(ContaGerencial.id)
    for c in session.exec(query).all():
        base = {
            "id": c.id, "numero_lancamento": c.numero_lancamento, "conta_bancaria": c.conta_bancaria,
            "valor": c.valor_pago if c.valor_pago is not None else c.valor_total,
            "data_pagamento": c.data_pagamento.isoformat() if c.data_pagamento else None,
        }
        conta_id, regra = casar_conta_corrente(c.conta_bancaria, refs)
        if conta_id is not None:
            plano.mudancas.append({**base, "para": conta_id, "regra": regra})
        else:
            motivo = ("mais de uma conta da fazenda parece com este texto" if regra == "ambiguo"
                      else "nenhuma conta cadastrada parece com este texto")
            plano.revisao.append({**base, "motivo": motivo})
    return plano


def aplicar(session: Session, plano: PlanoContaCorrente, lote: str) -> int:
    from fazenda.models import ContaGerencial
    from fazenda.rules.migracao_log import registrar_mudanca

    aplicadas = 0
    for m in plano.mudancas:
        registro = session.get(ContaGerencial, m["id"])
        if registro is None or registro.conta_corrente_id is not None:
            continue
        registrar_mudanca(
            session, fazenda_id=plano.fazenda_id, lote=lote, migracao=MIGRACAO, tabela="conta_gerencial",
            registro=registro, campo="conta_corrente_id", valor_depois=m["para"],
            motivo=f"casamento {m['regra']} de '{m['conta_bancaria']}'",
        )
        aplicadas += 1
    return aplicadas
