"""
Backfill dos itens das notas automáticas do histórico (Fase A, PR 2/3) — com
log e reversão. Regras em fazenda/rules/backfill_itens_automaticos.py.

Folha, férias, 13º, rescisões, guias de FGTS/DCTF, contratos, empreitas,
diárias, vales e caixa do funcionário lançados ANTES das contas automáticas
não têm item nem conta: caem em "não classificado". Este comando cria os
itens (folha pelo bruto, encargos, retidos, vale) na conta padrão de cada
origem, sem mudar `valor_total`/`valor_pago` e sem tocar nota que o usuário
já classificou à mão.

COMO USAR (uma fazenda por vez; configure antes as contas em Parâmetros
financeiros > Contas automáticas):

    python -m scripts.backfill_itens_automaticos --fazenda 3                  # só relata
    python -m scripts.backfill_itens_automaticos --fazenda 3 --csv plano.csv  # relata em CSV
    python -m scripts.backfill_itens_automaticos --fazenda 3 --aplicar        # grava (imprime o LOTE)
    python -m scripts.backfill_itens_automaticos --fazenda 3 --reverter LOTE  # mostra o que voltaria
    python -m scripts.backfill_itens_automaticos --fazenda 3 --reverter LOTE --aplicar

Ordem recomendada: script de impacto num dump → revisar com o dono → este
backfill (dry-run, depois --aplicar) → ligar a flag `financeiro_regras_v2`.
Com a flag desligada os relatórios ignoram estes itens: aplicar antes de ligar
não muda número nenhum.

⚠ Lê `DATABASE_URL` do ambiente. Rode primeiro num dump restaurado. Nenhum
nome ou documento de pessoa é impresso: só números de lançamento e valores.
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
        w.writerow(["acao", "numero_lancamento", "origem", "papel", "valor", "conta", "natureza", "motivo"])
        for nota in plano.criar:
            for item in nota["itens"]:
                w.writerow(["criar_item", nota["numero_lancamento"], nota["origem"], item.papel, item.valor,
                            item.codigo or "", item.natureza or "", ""])
        for p in plano.preencher:
            w.writerow(["preencher_conta", p["numero_lancamento"], "", p["papel"], "", p["codigo"], "", ""])
        for p in plano.preservadas:
            w.writerow(["preservar", p["numero_lancamento"], p.get("origem") or "", "", "", p.get("codigo_conta") or "",
                        "", p["motivo"]])


def executar(session: Session, fazenda_id: int, *, aplicar: bool, reverter: str | None = None,
             csv_saida: str | None = None, saida=print) -> dict:
    """Corpo do comando (os testes chamam direto com a sessão deles). Commit
    só com `aplicar=True`."""
    from fazenda.rules import backfill_itens_automaticos as bf
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

    plano = bf.planejar(session, fazenda_id)
    total_itens = sum(len(n["itens"]) for n in plano.criar)
    saida(f"Fazenda {fazenda_id}: {len(plano.criar)} nota(s) ganham {total_itens} item(ns); "
          f"{len(plano.preencher)} item(ns) ganham conta; {len(plano.preservadas)} preservada(s).")
    for nota in plano.criar:
        partes = ", ".join(f"{i.papel} {i.valor:.2f}{'' if i.codigo else ' (sem conta)'}" for i in nota["itens"])
        saida(f"  CRIAR {nota['numero_lancamento']} ({nota['origem']}, total {nota['total']:.2f}): {partes}")
    for p in plano.preservadas:
        saida(f"  PRESERVAR {p['numero_lancamento']}: {p['motivo']}")
    for origem, n in sorted(plano.sem_conta.items()):
        saida(f"  PENDÊNCIA: {n} item(ns) de custo sem conta automática para '{origem}' — configure antes de aplicar.")
    if csv_saida:
        _escrever_csv(csv_saida, plano)
        saida(f"CSV: {csv_saida}")
    lote = None
    linhas = 0
    if aplicar and (plano.criar or plano.preencher):
        lote = novo_lote("itens-auto")
        linhas = bf.aplicar(session, plano, lote, fazenda_id)
        session.commit()
        saida(f"Gravado: {linhas} linha(s) de log no lote {lote}. Para desfazer: --reverter {lote} --aplicar")
    else:
        session.rollback()
        if not aplicar:
            saida("Simulação: nada foi gravado. Use --aplicar para gravar.")
    return {"plano": plano, "lote": lote, "linhas": linhas}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fazenda", type=int, required=True, help="id da fazenda (uma por vez)")
    parser.add_argument("--aplicar", action="store_true", help="grava (sem isto, só relata)")
    parser.add_argument("--reverter", metavar="LOTE", help="desfaz um lote gravado antes")
    parser.add_argument("--csv", help="grava o plano em CSV (;)")
    args = parser.parse_args(argv)

    from fazenda.database import engine

    print(f"Banco: {engine.url.render_as_string(hide_password=True)}")
    with Session(engine) as session:
        executar(session, args.fazenda, aplicar=args.aplicar, reverter=args.reverter, csv_saida=args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
