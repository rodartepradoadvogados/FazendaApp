"""idempotencia_chave: cache de resposta por Idempotency-Key, pra reenvio da
fila offline do app de campo (frontend/lib/offline.ts) não duplicar um
lançamento quando a resposta de um POST se perde por queda de conexão.

Ver fazenda/models/idempotencia.py e o middleware em main.py (_idempotencia).

Revision ID: 8df6afc48295
Revises: b20df48b733a
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8df6afc48295'
down_revision: Union[str, Sequence[str], None] = 'b20df48b733a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'idempotencia_chave',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chave', sa.String(), nullable=False),
        sa.Column('metodo', sa.String(), nullable=False),
        sa.Column('caminho', sa.String(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('resposta_json', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_idempotencia_chave_chave'), 'idempotencia_chave', ['chave'])
    op.create_index(op.f('ix_idempotencia_chave_fazenda_id'), 'idempotencia_chave', ['fazenda_id'])
    op.create_index(
        'uq_idempotencia_chave_metodo_caminho', 'idempotencia_chave', ['chave', 'metodo', 'caminho'], unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_idempotencia_chave_metodo_caminho', table_name='idempotencia_chave')
    op.drop_index(op.f('ix_idempotencia_chave_fazenda_id'), table_name='idempotencia_chave')
    op.drop_index(op.f('ix_idempotencia_chave_chave'), table_name='idempotencia_chave')
    op.drop_table('idempotencia_chave')
