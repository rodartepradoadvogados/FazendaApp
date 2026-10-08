"""
Liga os pagamentos do histórico à conta corrente por FK (Fase A, PR 6) — com log e reversão.

A migração `a7c4e2d9b351` só cria `conta_gerencial.conta_corrente_id` (vazia). Este comando
casa o texto livre `conta_bancaria` com as contas cadastradas da fazenda (exato →
normalizado → banco único; ver fazenda/rules/backfill_conta_corrente.py) e lista para
REVISÃO o que ficou ambíguo. Padrão: só RELATA (dry-run). `--aplicar` grava num lote do
`migracao_log_financeiro`; `--reverter LOTE --aplicar` desfaz. Nunca toca
valor_total/valor_pago e nunca sobrescreve um vínculo já gravado.

    python -m scripts.backfill_conta_corrente --fazenda 3                  # só relata
    python -m scripts.backfill_conta_corrente --fazenda 3 --csv revisao.csv
    python -m scripts.backfill_conta_corrente --fazenda 3 --aplicar         # grava (imprime o LOTE)
    python -m scripts.backfill_conta_corrente --fazenda 3 --reverter LOTE --aplicar

Depois de ligar: o que sobrou na revisão se resolve na API
`GET /financeiro/conta-corrente/revisao` + `PUT /financeiro/lancamentos/conta-corrente-lote`.

⚠ Lê `DATABASE_URL` do ambiente. Rode primeiro num dump restaurado.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlmodel import Session  # noqa: E402


def _escrever_csv(caminho: str, plano) -> None:
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["acao", "id", "numero_lancamento", "conta_bancaria", "valor", "data_pagamento", "conta_corrente_id", "motivo"])
        for m in plano.mudancas:
            w.writerow(["ligar", m["id"], m["numero_lancamento"] or "", m["conta_bancaria"], m["valor"],
                        m["data_pagamento"] or "", m["para"], m["regra"]])
        for r in plano.revisao:
            w.writerow(["revisar", r["id"], r["numero_lancamento"] or "", r["conta_bancaria"], r["valor"],
                        r["data_pagamento"] or "", "", r["motivo"]])


def executar(session: Session, fazenda_id: int, *, aplicar: bool, reverter: str | None = None,
             csv_saida: str | None = None, saida=print) -> dict:
    from fazenda.rules import backfill_conta_corrente
    from fazenda.rules.migracao_log import novo_lote, reverter_lote

    if reverter:
        resultado = reverter_lote(session, reverter, fazenda_id=fazenda_id, aplicar=aplicar)
        saida(f"Lote {reverter} (fazenda {fazenda_id}): {resultado.revertidas} linha(s) "
              f"{'revertidas' if aplicar else 'seriam revertidas'}; {len(resultado.conflitos)} conflito(s).")
        session.commit() if aplicar else session.rollback()
        return {"reversao": resultado}

    plano = backfill_conta_corrente.planejar(session, fazenda_id)
    saida(f"Fazenda {fazenda_id}: {len(plano.mudancas)} lançamento(s) a ligar, {len(plano.revisao)} para revisão.")
    for m in plano.mudancas:
        saida(f"  LIGAR #{m['id']} {m['numero_lancamento']} '{m['conta_bancaria']}' → conta {m['para']} ({m['regra']})")
    for r in plano.revisao:
        saida(f"  REVISAR #{r['id']} {r['numero_lancamento']} '{r['conta_bancaria']}' R$ {r['valor']}: {r['motivo']}")
    if csv_saida:
        _escrever_csv(csv_saida, plano)
        saida(f"CSV: {csv_saida}")
    lote, aplicadas = None, 0
    if aplicar and plano.mudancas:
        lote = novo_lote("conta-corrente")
        aplicadas = backfill_conta_corrente.aplicar(session, plano, lote)
        session.commit()
        saida(f"Gravado: {aplicadas} vínculo(s) no lote {lote}. Para desfazer: --reverter {lote} --aplicar")
    else:
        session.rollback()
        if not aplicar:
            saida("Dry-run: nada foi gravado. Use --aplicar para gravar.")
    return {"plano": plano, "lote": lote, "aplicadas": aplicadas}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fazenda", type=int, required=True, help="id da fazenda (uma por vez)")
    parser.add_argument("--aplicar", action="store_true", help="grava (sem isto, só relata)")
    parser.add_argument("--reverter", metavar="LOTE", help="desfaz um lote gravado antes")
    parser.add_argument("--csv", help="grava o plano e a lista de revisão em CSV (;)")
    args = parser.parse_args(argv)

    from fazenda.database import engine

    print(f"Banco: {engine.url.render_as_string(hide_password=True)}")
    with Session(engine) as session:
        executar(session, args.fazenda, aplicar=args.aplicar, reverter=args.reverter, csv_saida=args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
