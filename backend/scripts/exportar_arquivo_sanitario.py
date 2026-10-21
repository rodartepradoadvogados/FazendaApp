"""Exporta o arquivo do sanitário preventivo antigo para JSON — um arquivo por
tabela (fase F0 do plano "Sanitário Preventivo v2").

Lê o schema `arquivo_sanitario_2026` criado pela migração
`s0a1r2q3v4o5_arquivar_sanitario_preventivo` no Postgres e grava
`<diretorio>/<tabela>.json` com a lista de linhas (datas e decimais viram
texto). Em SQLite (dev/testes) lê as tabelas com o prefixo
`arquivo_sanitario_2026__`. Só lê; nunca altera o banco.

Roda À MÃO, depois do deploy da migração — nunca no boot da API.

Uso (o banco vem da variável de ambiente DATABASE_URL; nenhum segredo em
arquivo):

    DATABASE_URL=... python backend/scripts/exportar_arquivo_sanitario.py DIRETORIO [--fazenda-id N]

Com --fazenda-id, só as linhas daquela fazenda (tabelas sem coluna
fazenda_id saem inteiras e o resumo avisa).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

SCHEMA = "arquivo_sanitario_2026"
PREFIXO_SQLITE = "arquivo_sanitario_2026__"


def url_do_ambiente() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit("Defina DATABASE_URL no ambiente (o script não lê segredo de arquivo).")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def tabelas_do_arquivo(engine) -> dict[str, tuple[str, list[str]]]:
    """{nome curto: (nome qualificado no SQL, colunas)}."""
    insp = inspect(engine)
    saida: dict[str, tuple[str, list[str]]] = {}
    if engine.dialect.name == "postgresql":
        if SCHEMA not in insp.get_schema_names():
            return {}
        for t in sorted(insp.get_table_names(schema=SCHEMA)):
            saida[t] = (f'{SCHEMA}."{t}"', [c["name"] for c in insp.get_columns(t, schema=SCHEMA)])
    else:
        for t in sorted(insp.get_table_names()):
            if t.startswith(PREFIXO_SQLITE):
                saida[t[len(PREFIXO_SQLITE):]] = (f'"{t}"', [c["name"] for c in insp.get_columns(t)])
    return saida


def exportar(engine, diretorio: Path, fazenda_id: int | None = None) -> dict[str, int | str]:
    diretorio.mkdir(parents=True, exist_ok=True)
    resumo: dict[str, int | str] = {}
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
        for nome, (sql_nome, colunas) in tabelas_do_arquivo(engine).items():
            filtro, params = "", {}
            if fazenda_id is not None and "fazenda_id" in colunas:
                filtro, params = " WHERE fazenda_id = :f", {"f": fazenda_id}
            ordem = " ORDER BY id" if "id" in colunas else ""
            linhas = [dict(r) for r in conn.execute(text(f"SELECT * FROM {sql_nome}{filtro}{ordem}"), params).mappings()]
            (diretorio / f"{nome}.json").write_text(
                json.dumps(linhas, ensure_ascii=False, indent=1, default=str), encoding="utf-8",
            )
            resumo[nome] = len(linhas)
            if fazenda_id is not None and "fazenda_id" not in colunas:
                resumo[f"{nome} (aviso)"] = "sem coluna fazenda_id — exportada inteira"
    return resumo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("diretorio", type=Path, help="pasta de saída (criada se não existir)")
    ap.add_argument("--fazenda-id", type=int, default=None, help="só as linhas desta fazenda")
    args = ap.parse_args()
    engine = create_engine(url_do_ambiente())
    resumo = exportar(engine, args.diretorio, args.fazenda_id)
    if not resumo:
        sys.exit(f"Nenhuma tabela em {SCHEMA} — a migração s0a1r2q3v4o5 já rodou neste banco?")
    for nome, n in resumo.items():
        print(f"{nome}: {n}")
    print(f"\nArquivos em {args.diretorio.resolve()}")


if __name__ == "__main__":
    main()
