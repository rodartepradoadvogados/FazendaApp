"""
Backfill da natureza econômica do histórico (Fase A, PR 1) — com log e reversão.

POR QUE COMANDO E NÃO MIGRAÇÃO
------------------------------
A migração `e5a9c3f1b742` só cria as colunas (vazias). Classificar o passado
muda número de relatório da fazenda que ligar a flag `financeiro_regras_v2`, e
isso merece alguém olhando: o padrão aqui é RELATAR (dry-run) e só gravar com
`--aplicar`, uma fazenda por vez. Cada campo gravado vira uma linha em
`migracao_log_financeiro` (antes/depois, fazenda, lote, motivo), e o lote
inteiro volta com `--reverter LOTE`.

Regras (conservadoras) em fazenda/rules/backfill_natureza.py. Nunca toca
valor_total/valor_pago; nunca sobrescreve natureza já preenchida.

COMO USAR
---------
    python -m scripts.backfill_natureza_fin --fazenda 3                    # só relata
    python -m scripts.backfill_natureza_fin --fazenda 3 --csv plano.csv     # relata em CSV
    python -m scripts.backfill_natureza_fin --fazenda 3 --aplicar           # grava (imprime o LOTE)
    python -m scripts.backfill_natureza_fin --fazenda 3 --reverter LOTE     # mostra o que voltaria
    python -m scripts.backfill_natureza_fin --fazenda 3 --reverter LOTE --aplicar

⚠ Lê `DATABASE_URL` do ambiente. Rode primeiro num dump restaurado e confira o
relatório de impacto (scripts/impacto_relatorios_v2.py) antes de `--aplicar`.
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
        w.writerow(["acao", "tabela", "id", "numero_lancamento", "codigo", "valor", "de", "para", "motivo", "sugestao"])
        for m in plano.mudancas:
            w.writerow(["aplicar", m["tabela"], m["id"], m.get("numero_lancamento") or "", m.get("codigo") or "",
                        m.get("valor") if m.get("valor") is not None else "", m.get("de") or "", m["para"], m["motivo"], ""])
        for r in plano.revisao:
            w.writerow(["revisar", r["tabela"], ",".join(str(i) for i in r["ids"]), r.get("numero_lancamento") or "", "",
                        r.get("valor") if r.get("valor") is not None else "", "", "", r["motivo"], r.get("sugestao") or ""])
        for s in plano.sugestoes:
            w.writerow(["sugerir", "plano_conta_gerencial", "", "", s["codigo"], "", "", s["natureza_sugerida"],
                        f"{s['motivo']} (linha atual: {s['linha_dre'] or 'sem linha'})", s["nome"]])


def executar(session: Session, fazenda_id: int, *, aplicar: bool, reverter: str | None = None,
             csv_saida: str | None = None, saida=print) -> dict:
    """Corpo do comando, separado do argparse para os testes chamarem direto
    com a sessão deles. Faz commit só quando `aplicar=True`."""
    from fazenda.rules import backfill_natureza
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

    plano = backfill_natureza.planejar(session, fazenda_id)
    saida(f"Fazenda {fazenda_id}: {len(plano.mudancas)} mudança(s) a aplicar, "
          f"{len(plano.revisao)} para revisão, {len(plano.sugestoes)} sugestão(ões) no plano de contas.")
    for m in plano.mudancas:
        alvo = m.get("numero_lancamento") or m.get("codigo")
        saida(f"  APLICAR {m['tabela']}#{m['id']} ({alvo}) → {m['para']}: {m['motivo']}")
    for r in plano.revisao:
        saida(f"  REVISAR {r.get('numero_lancamento')} R$ {r.get('valor')}: {r['motivo']}")
    for s in plano.sugestoes:
        saida(f"  SUGERIR {s['codigo']} {s['nome']} → {s['natureza_sugerida']} ({s['motivo']})")
    if csv_saida:
        _escrever_csv(csv_saida, plano)
        saida(f"CSV: {csv_saida}")
    lote = None
    aplicadas = 0
    if aplicar and plano.mudancas:
        lote = novo_lote("natureza")
        aplicadas = backfill_natureza.aplicar(session, plano, lote)
        session.commit()
        saida(f"Gravado: {aplicadas} campo(s) no lote {lote}. Para desfazer: --reverter {lote} --aplicar")
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
    parser.add_argument("--csv", help="grava o plano/revisão/sugestões em CSV (;)")
    args = parser.parse_args(argv)

    from fazenda.database import engine

    print(f"Banco: {engine.url.render_as_string(hide_password=True)}")
    with Session(engine) as session:
        executar(session, args.fazenda, aplicar=args.aplicar, reverter=args.reverter, csv_saida=args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
