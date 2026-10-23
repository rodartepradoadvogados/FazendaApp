"""arquiva o sanitário PREVENTIVO antigo (vacinas e exames) no schema arquivo_sanitario_2026

Migração A do plano "Sanitário Preventivo v2" (fase F1). O módulo antigo de
vacinas e exames (calendário/regras, eventos sanitários, cronogramas, lista de
espera, ocorrências, aplicações e exames preventivos, checklist) saiu do código.
Nada é apagado de verdade: tudo vai para um arquivo somente leitura, exportável
por `scripts/exportar_arquivo_sanitario.py`.

POSTGRES (produção):
  1. `CREATE SCHEMA arquivo_sanitario_2026`.
  2. Derruba as FKs que CRUZAM a fronteira (uma ponta numa das 13 tabelas
     antigas, a outra fora delas: fazenda, pessoa, estoque, lote_estoque,
     usuario, doenca, principio_ativo...). O DDL de cada uma fica gravado em
     `arquivo_sanitario_2026._fks_removidas` para o downgrade. As FKs entre as
     próprias 13 continuam valendo dentro do schema.
  3. Linhas preventivas das tabelas COMPARTILHADAS são copiadas
     (`CREATE TABLE AS`) para o arquivo e só então apagadas:
       - sanidade: critério `CRITERIO_SANIDADE` (natureza preventivo de
         vacina/exame, vínculo com o cronograma, vacina pré-parto da Secagem
         [D2] e vacinas antigas do Ideagri, natureza NULL + categoria 'Vacina'
         [D1]) — SEMPRE excluindo BST, Indução de cio e qualquer linha nascida
         de protocolo (curativo, IATF, indução);
       - aplicacao_agendada: `CRITERIO_APLICACAO_AGENDADA`;
       - evento_realizado: `CRITERIO_EVENTO_REALIZADO`;
       - parametro_fazenda: `CHAVES_PARAMETRO`;
       - checklist_template_item: só os tipos 'vacina'/'exame' (o tipo
         'curativo' é do protocolo curativo e fica).
     movimento_estoque e conta_gerencial NÃO são tocados (estoque "como está";
     o vínculo soft fica no arquivo).
  4. D3: `protocolo_sanitario.finalidade='preventivo'` vira 'curativo' (os ids
     ficam em `arquivo_sanitario_2026.protocolo_finalidade_preventiva`).
  5. `ALTER TABLE ... SET SCHEMA arquivo_sanitario_2026` nas 13 tabelas
     (índices, constraints, sequências e policies de RLS vão junto).
  6. Tira o acesso do role da API (`cowdata_app`, se existir) ao schema.

SQLITE (suíte de testes / dev local): não há schema; as tabelas antigas são
RENOMEADAS com o prefixo `arquivo_sanitario_2026__` (nada é apagado) e as
cópias das linhas compartilhadas usam o mesmo prefixo. Mesmo critério.

DOWNGRADE devolve tudo: tabelas de volta ao public (ou ao nome original),
FKs recriadas a partir de `_fks_removidas`, linhas reinseridas nas tabelas
compartilhadas (sem sobrescrever conflito), finalidade 'preventivo' restaurada,
cópias e schema removidos.

ATENÇÃO NO DEPLOY: esta migração tem de ir no MESMO deploy do código que tirou
os models antigos — senão o `create_all` do boot recria as 13 tabelas vazias.

Revision ID: s0a1r2q3v4o5
Revises: m4n5o6p7q8r9
Create Date: 2026-10-21 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s0a1r2q3v4o5"
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None

SCHEMA = "arquivo_sanitario_2026"
PREFIXO_SQLITE = "arquivo_sanitario_2026__"
ROLE_API = "cowdata_app"

# Ordem filhas -> pais (a do SET SCHEMA; o downgrade usa a inversa).
TABELAS_EXCLUSIVAS = (
    "cronograma_sanitario_checklist_item",
    "cronograma_sanitario_vinculo",
    "cronograma_sanitario_log",
    "cronograma_sanitario_aplicacao_animal",
    "cronograma_sanitario_aplicacao",
    "cronograma_sanitario_animal",
    "cronograma_sanitario",
    "calendario_sanitario_checklist_item",
    "calendario_sanitario",
    "exame_resultado",
    "evento_sanitario",
    "exame_definicao",
    "rotina_lista_espera_estado",
)

# BST e Indução de cio também gravam Sanidade.natureza='preventivo' (agenda.py
# /bst/aplicar e reproducao.py /inducao-cio) e NUNCA entram no arquivo. O BST
# confirmado pela Agenda (aplicação programada) nasce sem `atividade`, por isso
# o produto também é conferido (mesmos marcadores de agenda.MARCADORES_BST,
# em LIKE — mais largo, o lado seguro: na dúvida a linha fica).
_NAO_E_BST_NEM_INDUCAO = """
    COALESCE(atividade, '') NOT IN ('BST', 'Indução de cio')
    AND LOWER(COALESCE(produto, '')) NOT LIKE '%bst%'
    AND LOWER(COALESCE(produto, '')) NOT LIKE '%lactotropi%'
    AND LOWER(COALESCE(produto, '')) NOT LIKE '%boostin%'
    AND LOWER(COALESCE(produto, '')) NOT LIKE '%somatotropina%'
"""

# `{vinculo_cronograma}` vira o OR do vínculo com cronograma_sanitario_aplicacao_animal
# quando a tabela existe (ou some, quando não existe).
CRITERIO_SANIDADE = (
    "("
    "  (natureza = 'preventivo')"
    "  {vinculo_cronograma}"
    "  OR atividade = 'Vacina pré-parto' OR obs = 'Vacina pré-parto'"
    "  OR (natureza IS NULL AND categoria = 'Vacina')"
    ")"
    " AND protocolo_sanitario_lancamento_id IS NULL"
    " AND protocolo_iatf_lancamento_id IS NULL"
    " AND protocolo_inducao_lancamento_id IS NULL"
    " AND " + _NAO_E_BST_NEM_INDUCAO
)
VINCULO_CRONOGRAMA = (
    "OR id IN (SELECT sanidade_id FROM {tabela} WHERE sanidade_id IS NOT NULL)"
)
CRITERIO_APLICACAO_AGENDADA = (
    "("
    "  (natureza = 'preventivo' AND (observacao LIKE 'Preventivo:%' OR observacao LIKE 'Baixa retroativa:%'))"
    "  OR observacao = 'Vacina pré-parto'"
    ")"
    " AND " + _NAO_E_BST_NEM_INDUCAO.replace("atividade", "NULL")
)
CRITERIO_EVENTO_REALIZADO = (
    "evento_id LIKE 'cronograma_sanitario%'"
    " OR evento_id LIKE 'evento_sanitario_%'"
    " OR evento_id LIKE 'calendario_sanitario_%'"
    " OR evento_id LIKE 'vacina_pre_parto_%'"
)
CHAVES_PARAMETRO = (
    "janela_eventos_sanitarios_passado",
    "janela_eventos_sanitarios_futuro",
    "cronograma_sanitario_dias_aviso",
    "cronograma_sanitario_min_animais_agrupamento",
    "cronograma_sanitario_janela_agrupamento_dias",
    "usar_ocorrencia_universal",
    "lista_espera_rotina_ativa",
    "lista_espera_dias_antecedencia",
    "lista_espera_aviso_diario",
)
CRITERIO_PARAMETRO = "chave IN (" + ", ".join(f"'{c}'" for c in CHAVES_PARAMETRO) + ")"
# checklist_template_item FICA no public: o tipo "curativo" é do protocolo
# curativo (GET /cadastro/checklist-template). Só "vacina"/"exame" saem.
CRITERIO_CHECKLIST_TEMPLATE = "tipo IN ('vacina', 'exame')"

# (tabela compartilhada, nome da cópia no arquivo)
COPIAS = (
    ("sanidade", "sanidade_preventiva"),
    ("aplicacao_agendada", "aplicacao_agendada_preventiva"),
    ("evento_realizado", "evento_realizado_preventivo"),
    ("parametro_fazenda", "parametro_fazenda_preventivo"),
    ("checklist_template_item", "checklist_template_item_preventivo"),
)
COPIA_D3 = "protocolo_finalidade_preventiva"


def _pg(bind) -> bool:
    return bind.dialect.name == "postgresql"


def arquivado(bind, nome: str) -> str:
    """Nome qualificado de uma tabela do arquivo no dialeto da conexão."""
    return f"{SCHEMA}.{nome}" if _pg(bind) else f"{PREFIXO_SQLITE}{nome}"


def criterio_sanidade(tem_tabela_cronograma: bool, tabela_cronograma: str = "cronograma_sanitario_aplicacao_animal") -> str:
    vinculo = VINCULO_CRONOGRAMA.format(tabela=tabela_cronograma) if tem_tabela_cronograma else ""
    return CRITERIO_SANIDADE.format(vinculo_cronograma=vinculo)


def criterios(tem_tabela_cronograma: bool, tabela_cronograma: str = "cronograma_sanitario_aplicacao_animal") -> dict[str, str]:
    """WHERE de cada tabela compartilhada — reaproveitado pelo relatório (F0)."""
    return {
        "sanidade": criterio_sanidade(tem_tabela_cronograma, tabela_cronograma),
        "aplicacao_agendada": CRITERIO_APLICACAO_AGENDADA,
        "evento_realizado": CRITERIO_EVENTO_REALIZADO,
        "parametro_fazenda": CRITERIO_PARAMETRO,
        "checklist_template_item": CRITERIO_CHECKLIST_TEMPLATE,
    }


def _tabelas(bind, schema: str | None = None) -> set[str]:
    return set(sa.inspect(bind).get_table_names(schema=schema))


def _colunas(bind, tabela: str, schema: str | None = None) -> list[str]:
    return [c["name"] for c in sa.inspect(bind).get_columns(tabela, schema=schema)]


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------
def upgrade() -> None:
    bind = op.get_bind()
    pg = _pg(bind)
    publicas = _tabelas(bind)
    exclusivas = [t for t in TABELAS_EXCLUSIVAS if t in publicas]

    if pg:
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        op.execute(sa.text(
            f"COMMENT ON SCHEMA {SCHEMA} IS 'Sanitário preventivo antigo (até 2026) — somente leitura e exportação "
            f"(scripts/exportar_arquivo_sanitario.py). Não é lido pela API.'"
        ))
        _derrubar_fks_que_cruzam(bind, exclusivas)

    # Linhas preventivas das tabelas compartilhadas: copia, depois apaga.
    where = criterios("cronograma_sanitario_aplicacao_animal" in publicas)
    for tabela, copia in COPIAS:
        if tabela not in publicas:
            continue
        destino = arquivado(bind, copia)
        op.execute(sa.text(f"CREATE TABLE IF NOT EXISTS {destino} AS SELECT * FROM {tabela} WHERE {where[tabela]}"))
        op.execute(sa.text(f"DELETE FROM {tabela} WHERE id IN (SELECT id FROM {destino})"))

    # D3: protocolo de etapas com finalidade "preventivo" vira "curativo".
    # (`finalidade` nasceu por `_migrar_colunas`, fora do Alembic: um banco
    # erguido só pelas migrações pode não ter a coluna — aí não há o que mudar.)
    if "protocolo_sanitario" in publicas and "finalidade" in _colunas(bind, "protocolo_sanitario"):
        destino = arquivado(bind, COPIA_D3)
        op.execute(sa.text(
            f"CREATE TABLE IF NOT EXISTS {destino} AS SELECT id FROM protocolo_sanitario WHERE finalidade = 'preventivo'"
        ))
        op.execute(sa.text("UPDATE protocolo_sanitario SET finalidade = 'curativo' WHERE finalidade = 'preventivo'"))

    # As 13 tabelas exclusivas saem do public.
    for tabela in exclusivas:
        if pg:
            op.execute(sa.text(f"ALTER TABLE public.{tabela} SET SCHEMA {SCHEMA}"))
        else:
            op.execute(sa.text(f"ALTER TABLE {tabela} RENAME TO {PREFIXO_SQLITE}{tabela}"))

    if pg:
        op.execute(sa.text(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE_API}') THEN "
            f"REVOKE ALL ON SCHEMA {SCHEMA} FROM {ROLE_API}; END IF; END $$"
        ))


def _derrubar_fks_que_cruzam(bind, exclusivas: list[str]) -> None:
    op.execute(sa.text(
        f"CREATE TABLE IF NOT EXISTS {SCHEMA}._fks_removidas "
        "(tabela TEXT NOT NULL, nome TEXT NOT NULL, ddl TEXT NOT NULL)"
    ))
    if not exclusivas:
        return
    conjunto = set(exclusivas)
    linhas = bind.execute(sa.text("""
        SELECT c.conname, cl.relname AS tabela, ref.relname AS referenciada, pg_get_constraintdef(c.oid) AS definicao
        FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace
        JOIN pg_class ref ON ref.oid = c.confrelid
        WHERE c.contype = 'f' AND n.nspname = 'public'
          AND (cl.relname = ANY(:tabelas) OR ref.relname = ANY(:tabelas))
        ORDER BY cl.relname, c.conname
    """), {"tabelas": list(conjunto)}).all()
    for nome, tabela, referenciada, definicao in linhas:
        if (tabela in conjunto) == (referenciada in conjunto):
            continue  # FK interna às 13 (vai junto para o schema) — fica
        ddl = f'ALTER TABLE public.{tabela} ADD CONSTRAINT "{nome}" {definicao}'
        bind.execute(
            sa.text(f"INSERT INTO {SCHEMA}._fks_removidas (tabela, nome, ddl) VALUES (:t, :n, :d)"),
            {"t": tabela, "n": nome, "d": ddl},
        )
        op.execute(sa.text(f'ALTER TABLE public.{tabela} DROP CONSTRAINT "{nome}"'))


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------
def downgrade() -> None:
    bind = op.get_bind()
    pg = _pg(bind)
    if pg:
        existe = bind.execute(
            sa.text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"), {"s": SCHEMA}
        ).first()
        if not existe:
            return
        no_arquivo = _tabelas(bind, schema=SCHEMA)
    else:
        no_arquivo = {t[len(PREFIXO_SQLITE):] for t in _tabelas(bind) if t.startswith(PREFIXO_SQLITE)}

    # Tabelas exclusivas de volta (pais primeiro).
    for tabela in reversed(TABELAS_EXCLUSIVAS):
        if tabela not in no_arquivo:
            continue
        if pg:
            op.execute(sa.text(f"ALTER TABLE {SCHEMA}.{tabela} SET SCHEMA public"))
        else:
            op.execute(sa.text(f"ALTER TABLE {PREFIXO_SQLITE}{tabela} RENAME TO {tabela}"))

    if pg and "_fks_removidas" in no_arquivo:
        for (ddl,) in bind.execute(sa.text(f"SELECT ddl FROM {SCHEMA}._fks_removidas")).all():
            op.execute(sa.text(ddl))
        op.execute(sa.text(f"DROP TABLE {SCHEMA}._fks_removidas"))

    publicas = _tabelas(bind)
    for tabela, copia in COPIAS:
        if copia not in no_arquivo or tabela not in publicas:
            continue
        origem = arquivado(bind, copia)
        cols_copia = _colunas(bind, copia, schema=SCHEMA) if pg else _colunas(bind, f"{PREFIXO_SQLITE}{copia}")
        cols = [c for c in _colunas(bind, tabela) if c in set(cols_copia)]
        lista = ", ".join(f'"{c}"' for c in cols)
        if pg:
            op.execute(sa.text(f"INSERT INTO {tabela} ({lista}) SELECT {lista} FROM {origem} ON CONFLICT DO NOTHING"))
        else:
            op.execute(sa.text(f"INSERT OR IGNORE INTO {tabela} ({lista}) SELECT {lista} FROM {origem}"))
        op.execute(sa.text(f"DROP TABLE {origem}"))

    if COPIA_D3 in no_arquivo:
        origem = arquivado(bind, COPIA_D3)
        if "protocolo_sanitario" in publicas:
            op.execute(sa.text(
                f"UPDATE protocolo_sanitario SET finalidade = 'preventivo' WHERE id IN (SELECT id FROM {origem})"
            ))
        op.execute(sa.text(f"DROP TABLE {origem}"))

    if pg:
        op.execute(sa.text(f"DROP SCHEMA IF EXISTS {SCHEMA}"))
