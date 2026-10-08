"""
Cartão por item no histórico (Fase A, PR 5) — com log e reversão, sem duplicar o saldo.

A migração `b9d3f5a1c864` só cria as colunas. Este comando dá uma NOTA a cada compra de
cartão que ainda não tem (regras em fazenda/rules/backfill_cartao.py):

  - fatura aberta/fechada: nota em aberto, paga depois pela fatura;
  - fatura já paga pela nota genérica "Fatura X": nota da compra já paga, SEM conta
    bancária (só classifica a DRE pela conta e pela data da compra); a genérica vira
    natureza OBRIGACAO (fora da DRE) e continua sendo o único movimento de dinheiro —
    saldo, Caixa Real e Fluxo não mudam;
  - o resto vai para a lista de revisão.

Padrão: só RELATA (dry-run). `--aplicar` grava num lote do `migracao_log_financeiro`
(exige a flag `financeiro_regras_v2` ligada na fazenda); `--reverter LOTE --aplicar`
apaga as notas criadas e devolve a natureza da genérica (nota de fatura aberta que já foi
paga depois do backfill vira conflito e fica).

    python -m scripts.backfill_cartao_por_item --fazenda 3                 # só relata
    python -m scripts.backfill_cartao_por_item --fazenda 3 --csv cartao.csv
    python -m scripts.backfill_cartao_por_item --fazenda 3 --aplicar        # grava (imprime o LOTE)
    python -m scripts.backfill_cartao_por_item --fazenda 3 --reverter LOTE --aplicar

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
        w.writerow(["acao", "fatura_id", "competencia", "compra_id", "descricao", "valor", "data_compra", "nota_generica", "motivo"])
        for n in plano.notas:
            w.writerow([n["tipo"], n["fatura_id"], n["competencia"], n["compra_id"], n["descricao"], n["valor"],
                        n["data_compra"], n["generica_id"] or "", ""])
        for g in plano.genericas:
            w.writerow(["generica_obrigacao", g["fatura_id"], g["competencia"], "", "", g["valor"], "", g["numero_lancamento"], ""])
        for r in plano.revisao:
            w.writerow(["revisar", r["fatura_id"], r["competencia"], "", "", r["valor"], "", "", r["motivo"]])


def executar(session: Session, fazenda_id: int, *, aplicar: bool, reverter: str | None = None,
             csv_saida: str | None = None, saida=print) -> dict:
    from fazenda.rules import backfill_cartao
    from fazenda.rules.migracao_log import novo_lote, reverter_lote
    from fazenda.rules.parametros import regras_v2_ativas

    if reverter:
        resultado = reverter_lote(session, reverter, fazenda_id=fazenda_id, aplicar=aplicar)
        saida(f"Lote {reverter} (fazenda {fazenda_id}): {resultado.revertidas} linha(s) "
              f"{'revertidas' if aplicar else 'seriam revertidas'}; {len(resultado.conflitos)} conflito(s).")
        for c in resultado.conflitos:
            saida(f"  CONFLITO {c['tabela']}#{c['id']}.{c['campo']}: mudou depois do backfill — não mexi.")
        session.commit() if aplicar else session.rollback()
        return {"reversao": resultado}

    plano = backfill_cartao.planejar(session, fazenda_id)
    pagas = sum(1 for n in plano.notas if n["tipo"] == "nota_paga")
    saida(f"Fazenda {fazenda_id}: {len(plano.notas)} nota(s) de compra a criar ({pagas} de fatura já paga), "
          f"{len(plano.genericas)} nota(s) genérica(s) → OBRIGACAO, {len(plano.revisao)} para revisão.")
    for n in plano.notas:
        saida(f"  {n['tipo'].upper()} fatura {n['competencia']} compra #{n['compra_id']} {n['descricao']} R$ {n['valor']}")
    for g in plano.genericas:
        saida(f"  GENÉRICA {g['numero_lancamento']} (R$ {g['valor']}) → OBRIGACAO (sai da DRE; o dinheiro continua nela)")
    for r in plano.revisao:
        saida(f"  REVISAR fatura {r['competencia']} R$ {r['valor']}: {r['motivo']}")
    if csv_saida:
        _escrever_csv(csv_saida, plano)
        saida(f"CSV: {csv_saida}")
    lote, resumo = None, {"notas_criadas": 0, "genericas_marcadas": 0}
    if aplicar and not regras_v2_ativas(session, fazenda_id):
        session.rollback()
        saida("Recusado: ligue a flag financeiro_regras_v2 desta fazenda antes de aplicar "
              "(sem ela, as notas novas contariam em dobro nos relatórios antigos).")
        return {"plano": plano, "lote": None, "recusado": True, **resumo}
    if aplicar and (plano.notas or plano.genericas):
        lote = novo_lote("cartao")
        resumo = backfill_cartao.aplicar(session, plano, lote)
        session.commit()
        saida(f"Gravado: {resumo['notas_criadas']} nota(s) e {resumo['genericas_marcadas']} genérica(s) no lote {lote}. "
              f"Para desfazer: --reverter {lote} --aplicar")
    else:
        session.rollback()
        if not aplicar:
            saida("Dry-run: nada foi gravado. Use --aplicar para gravar.")
    return {"plano": plano, "lote": lote, **resumo}


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
