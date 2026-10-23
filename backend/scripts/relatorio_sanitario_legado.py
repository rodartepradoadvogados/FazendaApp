"""Relatório SOMENTE LEITURA do sanitário preventivo antigo — o que a migração
`s0a1r2q3v4o5_arquivar_sanitario_preventivo` arquiva (fase F0 do plano
"Sanitário Preventivo v2").

Conta, por fazenda:
  - as linhas de cada uma das 13 tabelas exclusivas do módulo antigo;
  - as linhas das tabelas COMPARTILHADAS que entram no arquivo (sanidade,
    aplicacao_agendada, evento_realizado, parametro_fazenda), com o critério
    EXATO da migração (importado do próprio arquivo da migração — uma fonte só);
  - a quebra da sanidade por motivo (natureza preventivo, vínculo com
    cronograma, vacina pré-parto da Secagem [D2], vacina Ideagri natureza NULL
    [D1]) e quantas linhas de BST e de Indução de cio FICAM (prova de que não
    entram no arquivo);
  - os protocolos de etapas com finalidade 'preventivo' que viram 'curativo' (D3).
E lista algumas linhas de amostra da sanidade para o dono aprovar.

Funciona antes da migração (lê o public) e depois (lê o schema
arquivo_sanitario_2026 / as tabelas com prefixo no SQLite). Nunca escreve.

Uso (o banco vem da variável de ambiente DATABASE_URL; nada de segredo em
arquivo):

    DATABASE_URL=... python backend/scripts/relatorio_sanitario_legado.py [--amostras 10] [--json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

_MIGRACAO = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "s0a1r2q3v4o5_arquivar_sanitario_preventivo.py"
)


def carregar_migracao():
    """Importa o arquivo da migração A só para reaproveitar as constantes de critério."""
    spec = importlib.util.spec_from_file_location("migracao_arquivo_sanitario", _MIGRACAO)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def url_do_ambiente() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit("Defina DATABASE_URL no ambiente (o script não lê segredo de arquivo).")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _contar_por_fazenda(conn, tabela_sql: str, colunas: list[str], where: str | None = None) -> dict:
    filtro = f" WHERE {where}" if where else ""
    if "fazenda_id" in colunas:
        linhas = conn.execute(text(f"SELECT fazenda_id, COUNT(*) FROM {tabela_sql}{filtro} GROUP BY fazenda_id")).all()
        return {("sem_fazenda" if f is None else int(f)): int(n) for f, n in linhas}
    (n,) = conn.execute(text(f"SELECT COUNT(*) FROM {tabela_sql}{filtro}")).one()
    return {"(tabela sem fazenda_id)": int(n)} if n else {}


def montar_relatorio(engine, amostras: int = 10) -> dict:
    m = carregar_migracao()
    pg = engine.dialect.name == "postgresql"
    insp = inspect(engine)
    publicas = set(insp.get_table_names())
    arquivo = set(insp.get_table_names(schema=m.SCHEMA)) if pg and m.SCHEMA in insp.get_schema_names() else {
        t[len(m.PREFIXO_SQLITE):] for t in publicas if t.startswith(m.PREFIXO_SQLITE)
    }
    ja_arquivado = bool(arquivo)

    def nome_arquivo(t: str) -> str:
        return f"{m.SCHEMA}.{t}" if pg else f"{m.PREFIXO_SQLITE}{t}"

    def colunas_arquivo(t: str) -> list[str]:
        return [c["name"] for c in (insp.get_columns(t, schema=m.SCHEMA) if pg else insp.get_columns(f"{m.PREFIXO_SQLITE}{t}"))]

    rel: dict = {
        "estado": "depois da migração (lendo o arquivo)" if ja_arquivado else "antes da migração (lendo o public)",
        "tabelas_exclusivas": {}, "linhas_compartilhadas": {}, "sanidade_por_motivo": {},
        "ficam_no_public": {}, "d3_protocolos_preventivo_para_curativo": {}, "amostras_sanidade": [],
    }
    with engine.connect() as conn:
        if pg:
            conn.execute(text("SET TRANSACTION READ ONLY"))

        for t in m.TABELAS_EXCLUSIVAS:
            if t in publicas:
                rel["tabelas_exclusivas"][t] = _contar_por_fazenda(conn, t, [c["name"] for c in insp.get_columns(t)])
            elif t in arquivo:
                rel["tabelas_exclusivas"][t] = _contar_por_fazenda(conn, nome_arquivo(t), colunas_arquivo(t))
            else:
                rel["tabelas_exclusivas"][t] = "não existe neste banco"

        if not ja_arquivado:
            tem_cron = "cronograma_sanitario_aplicacao_animal" in publicas
            where = m.criterios(tem_cron)
            for tabela, _copia in m.COPIAS:
                if tabela in publicas:
                    cols = [c["name"] for c in insp.get_columns(tabela)]
                    rel["linhas_compartilhadas"][tabela] = _contar_por_fazenda(conn, tabela, cols, where[tabela])
            if "sanidade" in publicas:
                cols = [c["name"] for c in insp.get_columns("sanidade")]
                exclusoes = (
                    " AND protocolo_sanitario_lancamento_id IS NULL AND protocolo_iatf_lancamento_id IS NULL"
                    " AND protocolo_inducao_lancamento_id IS NULL AND " + m._NAO_E_BST_NEM_INDUCAO
                )
                motivos = {
                    "natureza_preventivo": "natureza = 'preventivo'",
                    "vacina_pre_parto_secagem_D2": "(atividade = 'Vacina pré-parto' OR obs = 'Vacina pré-parto')",
                    "vacina_ideagri_natureza_nula_D1": "(natureza IS NULL AND categoria = 'Vacina')",
                }
                if tem_cron:
                    motivos["vinculo_cronograma"] = (
                        "id IN (SELECT sanidade_id FROM cronograma_sanitario_aplicacao_animal WHERE sanidade_id IS NOT NULL)"
                    )
                for chave, cond in motivos.items():
                    rel["sanidade_por_motivo"][chave] = _contar_por_fazenda(conn, "sanidade", cols, cond + exclusoes)
                rel["ficam_no_public"]["sanidade_bst"] = _contar_por_fazenda(
                    conn, "sanidade", cols,
                    "(atividade = 'BST' OR LOWER(COALESCE(produto, '')) LIKE '%bst%' "
                    "OR LOWER(COALESCE(produto, '')) LIKE '%lactotropi%' OR LOWER(COALESCE(produto, '')) LIKE '%boostin%' "
                    "OR LOWER(COALESCE(produto, '')) LIKE '%somatotropina%')",
                )
                rel["ficam_no_public"]["sanidade_inducao_cio"] = _contar_por_fazenda(
                    conn, "sanidade", cols, "atividade = 'Indução de cio'",
                )
                rel["ficam_no_public"]["sanidade_total_depois"] = _contar_por_fazenda(
                    conn, "sanidade", cols, f"NOT ({where['sanidade']})",
                )
                for linha in conn.execute(text(
                    "SELECT id, fazenda_id, numero_matriz, data_aplicacao, produto, categoria, natureza, atividade, obs "
                    f"FROM sanidade WHERE {where['sanidade']} ORDER BY data_aplicacao DESC, id DESC LIMIT :n"
                ), {"n": amostras}).mappings():
                    rel["amostras_sanidade"].append(dict(linha))
            if "protocolo_sanitario" in publicas:
                rel["d3_protocolos_preventivo_para_curativo"] = _contar_por_fazenda(
                    conn, "protocolo_sanitario", [c["name"] for c in insp.get_columns("protocolo_sanitario")],
                    "finalidade = 'preventivo'",
                )
        else:
            for tabela, copia in m.COPIAS:
                if copia in arquivo:
                    rel["linhas_compartilhadas"][tabela] = _contar_por_fazenda(conn, nome_arquivo(copia), colunas_arquivo(copia))
            if m.COPIA_D3 in arquivo:
                (n,) = conn.execute(text(f"SELECT COUNT(*) FROM {nome_arquivo(m.COPIA_D3)}")).one()
                rel["d3_protocolos_preventivo_para_curativo"] = {"total": int(n)}
            if "sanidade_preventiva" in arquivo:
                for linha in conn.execute(text(
                    "SELECT id, fazenda_id, numero_matriz, data_aplicacao, produto, categoria, natureza, atividade, obs "
                    f"FROM {nome_arquivo('sanidade_preventiva')} ORDER BY data_aplicacao DESC, id DESC LIMIT :n"
                ), {"n": amostras}).mappings():
                    rel["amostras_sanidade"].append(dict(linha))
    return rel


def _imprimir(rel: dict) -> None:
    print(f"Sanitário preventivo antigo — {rel['estado']}\n")
    print("== Tabelas exclusivas (vão inteiras para o arquivo) ==")
    for t, v in rel["tabelas_exclusivas"].items():
        print(f"  {t}: {v}")
    print("\n== Linhas das tabelas compartilhadas que entram no arquivo (por fazenda) ==")
    for t, v in rel["linhas_compartilhadas"].items():
        print(f"  {t}: {v}")
    if rel["sanidade_por_motivo"]:
        print("\n== Sanidade por motivo (um registro pode cair em mais de um) ==")
        for t, v in rel["sanidade_por_motivo"].items():
            print(f"  {t}: {v}")
    if rel["ficam_no_public"]:
        print("\n== Ficam no public (NÃO arquivados) ==")
        for t, v in rel["ficam_no_public"].items():
            print(f"  {t}: {v}")
    print(f"\n== D3: protocolos 'preventivo' -> 'curativo' == {rel['d3_protocolos_preventivo_para_curativo']}")
    if rel["amostras_sanidade"]:
        print("\n== Amostras de sanidade arquivada (para aprovação do dono) ==")
        for a in rel["amostras_sanidade"]:
            print("  " + " | ".join(f"{k}={a[k]}" for k in a))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--amostras", type=int, default=10, help="quantas linhas de sanidade listar (padrão 10)")
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    args = ap.parse_args()
    engine = create_engine(url_do_ambiente())
    rel = montar_relatorio(engine, args.amostras)
    if args.json:
        print(json.dumps(rel, ensure_ascii=False, indent=2, default=str))
    else:
        _imprimir(rel)


if __name__ == "__main__":
    main()
