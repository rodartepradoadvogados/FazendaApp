"""fechamento do mês (trilha append-only) e conciliação bancária (extrato importado)

Fase C5 dos Relatórios do Financeiro (docs/financeiro-fechamento-conciliacao.md):

- `fechamento_mes_evento` (APPEND-ONLY): cada "fechar"/"reabrir com motivo" de um mês,
  com quem, quando, retrato dos totais (JSON) e o SHA-256 dele. Gatilhos BEFORE
  UPDATE/DELETE barram até SQL cru (mesma função `cowdata_bloquear_append_only()` da
  migração c6f2a9d4e817 em PostgreSQL; RAISE(ABORT) em SQLite);
- `extrato_importacao`: um arquivo de extrato (OFX/CSV) importado numa conta corrente —
  período e saldo final informado pelo banco; o arquivo NÃO é guardado;
- `extrato_linha`: os movimentos do extrato e o pareamento com o sistema.

ADITIVA e reversível. Idempotente (o boot também cria as tabelas pelo create_all).
O downgrade remove gatilhos e tabelas (ATENÇÃO: apaga a trilha dos fechamentos e as
conciliações feitas — exporte o Pacote do contador antes de descer em produção).

Revision ID: d4e8b1c7a2f5
Revises: c6f2a9d4e817
Create Date: 2026-10-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e8b1c7a2f5'
down_revision: Union[str, Sequence[str], None] = 'c6f2a9d4e817'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRILHA = 'fechamento_mes_evento'
FUNCAO_PG = 'cowdata_bloquear_append_only'

INDICES = (
    ('fechamento_mes_evento', 'ix_fechamento_mes_evento_fazenda_id', ['fazenda_id']),
    ('fechamento_mes_evento', 'ix_fechamento_mes_evento_mes', ['mes']),
    ('extrato_importacao', 'ix_extrato_importacao_fazenda_id', ['fazenda_id']),
    ('extrato_importacao', 'ix_extrato_importacao_conta_corrente_id', ['conta_corrente_id']),
    ('extrato_linha', 'ix_extrato_linha_fazenda_id', ['fazenda_id']),
    ('extrato_linha', 'ix_extrato_linha_conta_corrente_id', ['conta_corrente_id']),
    ('extrato_linha', 'ix_extrato_linha_importacao_id', ['importacao_id']),
    ('extrato_linha', 'ix_extrato_linha_data', ['data']),
    ('extrato_linha', 'ix_extrato_linha_status', ['status']),
    ('extrato_linha', 'ix_extrato_linha_lancamento_id', ['lancamento_id']),
    ('extrato_linha', 'ix_extrato_linha_transferencia_id', ['transferencia_id']),
)


def _gatilhos(dialeto: str, tabela: str) -> list[str]:
    # Cópia deliberada de fazenda/models/juridico.py::ddl_gatilhos (a migração não
    # importa o código da aplicação).
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
    if not insp.has_table('fechamento_mes_evento'):
        op.create_table(
            'fechamento_mes_evento',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
            sa.Column('mes', sa.String(), nullable=False),
            sa.Column('acao', sa.String(), nullable=False),
            sa.Column('motivo', sa.String(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
            sa.Column('usuario_nome', sa.String(), nullable=True),
            sa.Column('retrato_json', sa.String(), nullable=True),
            sa.Column('retrato_sha256', sa.String(), nullable=True),
            sa.Column('pendencias_no_fechamento', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
        )
    if not insp.has_table('extrato_importacao'):
        op.create_table(
            'extrato_importacao',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
            sa.Column('conta_corrente_id', sa.Integer(), sa.ForeignKey('conta_corrente.id'), nullable=False),
            sa.Column('formato', sa.String(), nullable=False),
            sa.Column('data_inicio', sa.Date(), nullable=True),
            sa.Column('data_fim', sa.Date(), nullable=True),
            sa.Column('saldo_final', sa.Float(), nullable=True),
            sa.Column('data_saldo', sa.Date(), nullable=True),
            sa.Column('linhas_novas', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('linhas_repetidas', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
        )
    if not insp.has_table('extrato_linha'):
        op.create_table(
            'extrato_linha',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=False),
            sa.Column('conta_corrente_id', sa.Integer(), sa.ForeignKey('conta_corrente.id'), nullable=False),
            sa.Column('importacao_id', sa.Integer(), sa.ForeignKey('extrato_importacao.id'), nullable=True),
            sa.Column('data', sa.Date(), nullable=False),
            sa.Column('valor', sa.Float(), nullable=False),
            sa.Column('historico', sa.String(), nullable=True),
            sa.Column('documento', sa.String(), nullable=True),
            sa.Column('chave_dedup', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=False, server_default='pendente'),
            sa.Column('lancamento_id', sa.Integer(), sa.ForeignKey('conta_gerencial.id'), nullable=True),
            sa.Column('transferencia_id', sa.Integer(), sa.ForeignKey('transferencia_contas.id'), nullable=True),
            sa.Column('observacao', sa.String(), nullable=True),
            sa.Column('conciliado_por', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
            sa.Column('conciliado_em', sa.DateTime(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('fazenda_id', 'conta_corrente_id', 'chave_dedup', name='uq_extrato_linha_dedup'),
        )
    insp = sa.inspect(bind)
    for tabela, indice, colunas in INDICES:
        if indice not in {i['name'] for i in insp.get_indexes(tabela)}:
            op.create_index(indice, tabela, colunas)
    for cmd in _gatilhos(bind.dialect.name, TRILHA):
        op.execute(cmd)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table(TRILHA):
        if bind.dialect.name == 'postgresql':
            op.execute(f"DROP TRIGGER IF EXISTS trg_{TRILHA}_append_only ON {TRILHA}")
            # A função é compartilhada com aceite_termos/exportacao_relatorio_log
            # (c6f2a9d4e817): não se apaga aqui.
        elif bind.dialect.name == 'sqlite':
            op.execute(f"DROP TRIGGER IF EXISTS trg_{TRILHA}_sem_update")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{TRILHA}_sem_delete")
    for tabela in ('extrato_linha', 'extrato_importacao', 'fechamento_mes_evento'):
        if insp.has_table(tabela):
            existentes = {i['name'] for i in insp.get_indexes(tabela)}
            for t, indice, _c in INDICES:
                if t == tabela and indice in existentes:
                    op.drop_index(indice, table_name=tabela)
            op.drop_table(tabela)
