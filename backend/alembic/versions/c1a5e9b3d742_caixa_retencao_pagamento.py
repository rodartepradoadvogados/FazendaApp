"""caixa dos funcionarios: retencao no pagamento de quem nao e CLT

Coluna `origem_conta_id` em `caixa_movimento` e `caixa_time_movimento`: a conta (ContaGerencial) paga
cujo pagamento gerou a retencao (parcela de contrato/empreita, diaria). ADITIVA e idempotente.

Revision ID: c1a5e9b3d742
Revises: b9d3f7a1c528
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a5e9b3d742'
down_revision: Union[str, Sequence[str], None] = 'b9d3f7a1c528'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELAS = ('caixa_movimento', 'caixa_time_movimento')


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for t in TABELAS:
        if not insp.has_table(t):
            continue
        if 'origem_conta_id' not in {c['name'] for c in insp.get_columns(t)}:
            with op.batch_alter_table(t) as batch:
                batch.add_column(sa.Column('origem_conta_id', sa.Integer(), nullable=True))
        if f'ix_{t}_origem_conta_id' not in {i['name'] for i in sa.inspect(op.get_bind()).get_indexes(t)}:
            op.create_index(f'ix_{t}_origem_conta_id', t, ['origem_conta_id'])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for t in TABELAS:
        if not insp.has_table(t):
            continue
        if f'ix_{t}_origem_conta_id' in {i['name'] for i in insp.get_indexes(t)}:
            op.drop_index(f'ix_{t}_origem_conta_id', table_name=t)
        if 'origem_conta_id' in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(t)}:
            with op.batch_alter_table(t) as batch:
                batch.drop_column('origem_conta_id')
