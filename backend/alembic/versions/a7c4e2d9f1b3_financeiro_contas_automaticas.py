"""financeiro Fase A (PR 2/3): contas automáticas e itens gerados pelo sistema

- tabela nova `conta_padrao_origem` (fazenda, origem, conta gerencial,
  natureza): a conta padrão de cada origem de lançamento automático (folha,
  férias, 13º, rescisão, contrato, empreita, diária, vale, caixa do
  funcionário, encargos e retidos);
- coluna nova, nula, `lancamento_item.gerado_por`: o papel do item que o
  sistema criou numa nota automática (NULL = item lançado por gente).

ADITIVA, idempotente (tabela/coluna já criadas pelo `create_all` do boot não
abortam o upgrade) e SEM backfill: nenhuma linha existente é tocada. O
histórico ganha itens só pelo comando `scripts/backfill_itens_automaticos.py`
(simulação por padrão, com log em `migracao_log_financeiro`). O downgrade
remove os itens marcados com `gerado_por` (só existem por causa desta fase),
a coluna e a tabela.

Revision ID: a7c4e2d9f1b3
Revises: f3b8d1c6a9e2
Create Date: 2026-10-08 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c4e2d9f1b3'
down_revision: Union[str, Sequence[str], None] = 'f3b8d1c6a9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = 'conta_padrao_origem'


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('lancamento_item') and 'gerado_por' not in {c['name'] for c in insp.get_columns('lancamento_item')}:
        with op.batch_alter_table('lancamento_item') as batch:
            batch.add_column(sa.Column('gerado_por', sa.String(), nullable=True))
    if not insp.has_table(TABELA):
        op.create_table(
            TABELA,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
            sa.Column('origem', sa.String(), nullable=False),
            sa.Column('codigo_conta_gerencial', sa.String(), nullable=True),
            sa.Column('natureza_fin', sa.String(), nullable=True),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('fazenda_id', 'origem', name='uq_conta_padrao_origem_fazenda_origem'),
        )
        op.create_index('ix_conta_padrao_origem_fazenda_id', TABELA, ['fazenda_id'])
        op.create_index('ix_conta_padrao_origem_origem', TABELA, ['origem'])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        op.drop_index('ix_conta_padrao_origem_origem', table_name=TABELA)
        op.drop_index('ix_conta_padrao_origem_fazenda_id', table_name=TABELA)
        op.drop_table(TABELA)
    if insp.has_table('lancamento_item') and 'gerado_por' in {c['name'] for c in insp.get_columns('lancamento_item')}:
        # Os itens gerados pelo sistema só existem por causa desta fase: sem a
        # coluna, eles virariam itens "de gente" e o motor antigo os somaria.
        op.execute(sa.text("DELETE FROM lancamento_item WHERE gerado_por IS NOT NULL"))
        with op.batch_alter_table('lancamento_item') as batch:
            batch.drop_column('gerado_por')
