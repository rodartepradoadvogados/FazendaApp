"""caixa dos funcionarios: retencao com destino time/dividir

Colunas `caixa_retencao.time_id`, `caixa_retencao.pct_time` e
`caixa_time_movimento.folha_id`. ADITIVA e idempotente.

Revision ID: f7b1d5a9c346
Revises: e6a0c4f8b235
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7b1d5a9c346'
down_revision: Union[str, Sequence[str], None] = 'e6a0c4f8b235'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(insp, t):
    return {c['name'] for c in insp.get_columns(t)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    c = _cols(insp, 'caixa_retencao')
    with op.batch_alter_table('caixa_retencao') as batch:
        if 'time_id' not in c:
            batch.add_column(sa.Column('time_id', sa.Integer(), nullable=True))
        if 'pct_time' not in c:
            batch.add_column(sa.Column('pct_time', sa.Float(), nullable=False, server_default='50'))
    if 'folha_id' not in _cols(insp, 'caixa_time_movimento'):
        with op.batch_alter_table('caixa_time_movimento') as batch:
            batch.add_column(sa.Column('folha_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_caixa_time_movimento_folha_id'), 'caixa_time_movimento', ['folha_id'])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if 'folha_id' in _cols(insp, 'caixa_time_movimento'):
        if 'ix_caixa_time_movimento_folha_id' in {i['name'] for i in insp.get_indexes('caixa_time_movimento')}:
            op.drop_index('ix_caixa_time_movimento_folha_id', table_name='caixa_time_movimento')
        with op.batch_alter_table('caixa_time_movimento') as batch:
            batch.drop_column('folha_id')
    c = _cols(insp, 'caixa_retencao')
    with op.batch_alter_table('caixa_retencao') as batch:
        if 'pct_time' in c:
            batch.drop_column('pct_time')
        if 'time_id' in c:
            batch.drop_column('time_id')
