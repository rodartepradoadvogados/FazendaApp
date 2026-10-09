"""
Backfill das contas padrão de `vale` e `caixa_retencao` — com log e reversão.
Regras em fazenda/rules/backfill_contas_origem.py.

O plano de contas ganhou duas contas do sistema (migração d8b3f6a1c294 e
`rules/plano_padrao.py`): 3.03.01.16 Retenções e 3.03.01.17 Vales e
adiantamentos. Este comando grava `ContaPadraoOrigem` de `vale` → 3.03.01.17 e
`caixa_retencao` → 3.03.01.16 onde estiver vazia e, com `--repintar-itens`,
dá a conta aos itens antigos dos geradores de retenção/vale que estão SEM
conta. Nunca troca conta já configurada, nunca toca nota com item lançado por
gente e nunca muda `valor_total`/`valor_pago`.

COMO USAR (uma fazenda por vez):

    python -m scripts.backfill_contas_origem --fazenda 3                      # só relata
    python -m scripts.backfill_contas_origem --fazenda 3 --repintar-itens     # inclui os itens antigos
    python -m scripts.backfill_contas_origem --fazenda 3 --csv plano.csv      # relata em CSV
    python -m scripts.backfill_contas_origem --fazenda 3 --aplicar            # grava (imprime o LOTE)
    python -m scripts.backfill_contas_origem --fazenda 3 --reverter LOTE      # mostra o que voltaria
    python -m scripts.backfill_contas_origem --fazenda 3 --reverter LOTE --aplicar

Com a flag `financeiro_regras_v2` desligada os relatórios ignoram itens
gerados: aplicar antes de ligar a flag não muda número nenhum.

⚠ Lê `DATABASE_URL` do ambiente. Rode primeiro num dump restaurado. Nenhum
nome ou documento de pessoa é impresso: só números de lançamento.
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
        w.writerow(["acao", "origem_ou_papel", "numero_lancamento", "item_id", "conta", "motivo"])
        for p in plano.criar_origem:
            w.writerow(["criar_origem", p["origem"], "", "", p["codigo"], ""])
        for p in plano.preencher_origem:
            w.writerow(["preencher_origem", p["origem"], "", "", p["codigo"], ""])
        for p in plano.mantidas:
            w.writerow(["manter_origem", p["origem"], "", "", p.get("codigo") or "", p["motivo"]])
        for p in plano.repintar:
            w.writerow(["repintar_item", p["papel"], p["numero_lancamento"], p["item_id"], p["codigo"], ""])
        for p in plano.preservadas:
            w.writerow(["preservar_item", "", p["numero_lancamento"], p["item_id"], "", p["motivo"]])


def executar(session: Session, fazenda_id: int, *, aplicar: bool, reverter: str | None = None,
             repintar_itens: bool = False, csv_saida: str | None = None, saida=print) -> dict:
    """Corpo do comando (os testes chamam direto com a sessão deles). Commit
    só com `aplicar=True`."""
    from fazenda.rules import backfill_contas_origem as bf
    from fazenda.rules.migracao_log import novo_lote, reverter_lote

    session.info["fazenda_id"] = fazenda_id
    if reverter:
        resultado = reverter_lote(session, reverter, fazenda_id=fazenda_id, aplicar=aplicar)
        saida(f"Lote {reverter} (fazenda {fazenda_id}): {resultado.revertidas} linha(s) "
              f"{'revertidas' if aplicar else 'seriam revertidas'}; {resultado.ja_revertidas} já revertida(s); "
              f"{len(resultado.conflitos)} conflito(s); {len(resultado.nao_encontradas)} não encontrada(s).")
        for c in resultado.conflitos:
            saida(f"  CONFLITO {c['tabela']}#{c['id']}.{c['campo']}: hoje={c['valor_atual']!r}, "
                  f"backfill gravou={c['valor_gravado_pelo_backfill']!r} — não mexi.")
        if aplicar:
            session.commit()
        else:
            session.rollback()
        return {"reversao": resultado}

    plano = bf.planejar(session, fazenda_id, repintar_itens=repintar_itens)
    saida(f"Fazenda {fazenda_id}: {len(plano.criar_origem)} origem(ns) a criar, "
          f"{len(plano.preencher_origem)} a preencher, {len(plano.mantidas)} mantida(s); "
          f"{len(plano.repintar)} item(ns) a classificar, {len(plano.preservadas)} preservado(s).")
    for p in plano.criar_origem + plano.preencher_origem:
        saida(f"  ORIGEM {p['origem']} -> {p['codigo']}")
    for p in plano.mantidas:
        saida(f"  MANTER {p['origem']}: {p['motivo']}")
    for p in plano.repintar:
        saida(f"  ITEM {p['item_id']} (nota {p['numero_lancamento']}, {p['papel']}) -> {p['codigo']}")
    for p in plano.preservadas:
        saida(f"  PRESERVAR item {p['item_id']} (nota {p['numero_lancamento']}): {p['motivo']}")
    if csv_saida:
        _escrever_csv(csv_saida, plano)
        saida(f"CSV: {csv_saida}")
    lote = None
    linhas = 0
    if aplicar and (plano.criar_origem or plano.preencher_origem or plano.repintar):
        lote = novo_lote("contas-origem")
        linhas = bf.aplicar(session, plano, lote, fazenda_id)
        session.commit()
        saida(f"Gravado: {linhas} linha(s) de log no lote {lote}. Para desfazer: --reverter {lote} --aplicar")
    else:
        session.rollback()
        if not aplicar:
            saida("Simulação: nada foi gravado. Use --aplicar para gravar.")
        else:
            saida("Nada a gravar.")
    return {"plano": plano, "lote": lote, "linhas": linhas}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fazenda", type=int, required=True, help="id da fazenda (uma por vez)")
    parser.add_argument("--aplicar", action="store_true", help="grava (sem isto, só relata)")
    parser.add_argument("--reverter", metavar="LOTE", help="desfaz um lote gravado antes")
    parser.add_argument("--repintar-itens", action="store_true",
                        help="também classifica os itens antigos de retenção/vale que estão sem conta")
    parser.add_argument("--csv", help="grava o plano em CSV (;)")
    args = parser.parse_args(argv)

    from fazenda.database import engine

    print(f"Banco: {engine.url.render_as_string(hide_password=True)}")
    with Session(engine) as session:
        executar(session, args.fazenda, aplicar=args.aplicar, reverter=args.reverter,
                 repintar_itens=args.repintar_itens, csv_saida=args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
