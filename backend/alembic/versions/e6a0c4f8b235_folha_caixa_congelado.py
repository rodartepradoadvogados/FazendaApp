"""caixa dos funcionarios, fase 4: rodape do holerite congelado

Coluna `folha_pagamento.caixa_congelado` (JSON com saldo individual e parte estimada
no caixa do time no ato do pagamento). ADITIVA e idempotente.

Revision ID: e6a0c4f8b235
Revises: d5f9b3e7a124
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6a0c4f8b235'
down_revision: Union[str, Sequence[str], None] = 'd5f9b3e7a124'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if 'caixa_congelado' not in {c['name'] for c in insp.get_columns('folha_pagamento')}:
        with op.batch_alter_table('folha_pagamento') as batch:
            batch.add_column(sa.Column('caixa_congelado', sa.Text(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if 'caixa_congelado' in {c['name'] for c in insp.get_columns('folha_pagamento')}:
        with op.batch_alter_table('folha_pagamento') as batch:
            batch.drop_column('caixa_congelado')
