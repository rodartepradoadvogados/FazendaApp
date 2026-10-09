"""réguas de referência (parecer jurídico de 08/10/2026): aceites, exportações e erros reportados

- `aceite_termos` (APPEND-ONLY): aceite geral, de cláusula e do modal "Entendi" das réguas,
  com versão + SHA-256 do texto, IP, user-agent e data/hora UTC (parecer 6.1);
- `exportacao_relatorio_log` (APPEND-ONLY): quem exportou/compartilhou que relatório, quando,
  para quem, para quê, com que versão das réguas (parecer 6.2);
- `regua_erro_reportado`: botão "Reportar erro na faixa" (parecer 6.3/7.4).

As duas tabelas append-only ganham gatilhos BEFORE UPDATE/DELETE que barram até SQL cru
(PostgreSQL: função `cowdata_bloquear_append_only()`; SQLite: RAISE(ABORT)). Os mesmos
gatilhos nascem pelo `create_all` (ver fazenda/models/juridico.py), por isso a criação aqui
é idempotente: tabela já criada pelo boot não aborta, e os gatilhos são (re)criados.

ADITIVA e reversível: o downgrade remove gatilhos e tabelas (ATENÇÃO: apaga os registros de
prova — exporte os comprovantes antes de descer em produção).

Revision ID: c6f2a9d4e817
Revises: b9d3f5a1c864
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c6f2a9d4e817'
down_revision: Union[str, Sequence[str], None] = 'b9d3f5a1c864'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPEND_ONLY = ('aceite_termos', 'exportacao_relatorio_log')
FUNCAO_PG = 'cowdata_bloquear_append_only'

INDICES = (
    ('aceite_termos', 'ix_aceite_termos_usuario_id', ['usuario_id']),
    ('aceite_termos', 'ix_aceite_termos_fazenda_id', ['fazenda_id']),
    ('aceite_termos', 'ix_aceite_termos_tipo', ['tipo']),
    ('exportacao_relatorio_log', 'ix_exportacao_relatorio_log_fazenda_id', ['fazenda_id']),
    ('exportacao_relatorio_log', 'ix_exportacao_relatorio_log_usuario_id', ['usuario_id']),
    ('regua_erro_reportado', 'ix_regua_erro_reportado_fazenda_id', ['fazenda_id']),
    ('regua_erro_reportado', 'ix_regua_erro_reportado_usuario_id', ['usuario_id']),
    ('regua_erro_reportado', 'ix_regua_erro_reportado_regua_codigo', ['regua_codigo']),
    ('regua_erro_reportado', 'ix_regua_erro_reportado_status', ['status']),
)


def _gatilhos(dialeto: str, tabela: str) -> list[str]:
    # Cópia deliberada de fazenda/models/juridico.py::ddl_gatilhos — migração não
    # importa o código da aplicação (ele muda; a migração não pode mudar junto).
    if dialeto == 'postgresql':
        return [
            f"CREATE OR REPLACE FUNCTION {FUNCAO_PG}() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN RAISE EXCEPTION USING MESSAGE = TG_TABLE_NAME || ' é append-only: UPDATE/DELETE proibido'; END; $$",
            f"DROP TRIGGER IF EXISTS trg_{tabela}_append_only ON {tabela}",
            f"CREATE TRIGGER trg_{tabela}_append_only BEFORE UPDATE OR DELETE ON {tabela} "
            f"FOR EACH ROW EXECUTE PROCEDURE {FUNCAO_PG}()",
        ]
    if dialeto == 'sqlite':
        return [
            f"CREATE TRIGGER IF NOT EXISTS trg_{tabela}_sem_update BEFORE UPDATE ON {tabela} "
            f"BEGIN SELECT RAISE(ABORT, '{tabela} é append-only: UPDATE proibido'); END",
            f"CREATE TRIGGER IF NOT EXISTS trg_{tabela}_sem_delete BEFORE DELETE ON {tabela} "
            f"BEGIN SELECT RAISE(ABORT, '{tabela} é append-only: DELETE proibido'); END",
        ]
    return []


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table('aceite_termos'):
        op.create_table(
            'aceite_termos',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
            sa.Column('tipo', sa.String(), nullable=False),
            sa.Column('texto_chave', sa.String(), nullable=False),
            sa.Column('versao', sa.String(), nullable=False),
            sa.Column('sha256', sa.String(), nullable=False),
            sa.Column('ip', sa.String(), nullable=True),
            sa.Column('user_agent', sa.String(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
        )
    if not insp.has_table('exportacao_relatorio_log'):
        op.create_table(
            'exportacao_relatorio_log',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
            sa.Column('relatorio', sa.String(), nullable=False),
            sa.Column('formato', sa.String(), nullable=True),
            sa.Column('com_reguas', sa.Boolean(), nullable=False),
            sa.Column('destinatario', sa.String(), nullable=True),
            sa.Column('destinatario_tipo', sa.String(), nullable=True),
            sa.Column('finalidade', sa.String(), nullable=True),
            sa.Column('autorizacao_confirmada', sa.Boolean(), nullable=False),
            sa.Column('versao_reguas', sa.String(), nullable=True),
            sa.Column('rodape_versao', sa.String(), nullable=True),
            sa.Column('rodape_sha256', sa.String(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
        )
    if not insp.has_table('regua_erro_reportado'):
        op.create_table(
            'regua_erro_reportado',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
            sa.Column('regua_codigo', sa.String(), nullable=False),
            sa.Column('texto', sa.String(), nullable=False),
            sa.Column('versao_reguas', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('resposta', sa.String(), nullable=True),
            sa.Column('tratado_por_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
            sa.Column('tratado_em', sa.DateTime(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
        )
    insp = sa.inspect(bind)
    for tabela, indice, colunas in INDICES:
        if indice not in {i['name'] for i in insp.get_indexes(tabela)}:
            op.create_index(indice, tabela, colunas)
    for tabela in APPEND_ONLY:
        for cmd in _gatilhos(bind.dialect.name, tabela):
            op.execute(cmd)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for tabela in APPEND_ONLY:
        if not insp.has_table(tabela):
            continue
        if bind.dialect.name == 'postgresql':
            op.execute(f"DROP TRIGGER IF EXISTS trg_{tabela}_append_only ON {tabela}")
        elif bind.dialect.name == 'sqlite':
            op.execute(f"DROP TRIGGER IF EXISTS trg_{tabela}_sem_update")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{tabela}_sem_delete")
    if bind.dialect.name == 'postgresql':
        op.execute(f"DROP FUNCTION IF EXISTS {FUNCAO_PG}()")
    for tabela in ('regua_erro_reportado', 'exportacao_relatorio_log', 'aceite_termos'):
        if insp.has_table(tabela):
            existentes = {i['name'] for i in insp.get_indexes(tabela)}
            for t, indice, _c in INDICES:
                if t == tabela and indice in existentes:
                    op.drop_index(indice, table_name=tabela)
            op.drop_table(tabela)
