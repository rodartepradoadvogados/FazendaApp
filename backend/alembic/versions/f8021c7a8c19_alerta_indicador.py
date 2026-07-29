"""alerta_indicador: configuração de "avise-me se o indicador X passar de Y"

Ver fazenda/models/alerta_indicador.py e fazenda/api/routers/alertas_indicador.py.

Revision ID: f8021c7a8c19
Revises: 99b823147c9f
Create Date: 2026-07-29 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8021c7a8c19'
down_revision: Union[str, Sequence[str], None] = '99b823147c9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'alerta_indicador',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('indicador_chave', sa.String(), nullable=False),
        sa.Column('operador', sa.String(), nullable=False),
        sa.Column('valor_limite', sa.Float(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_alerta_indicador_usuario_id'), 'alerta_indicador', ['usuario_id'])
    op.create_index(op.f('ix_alerta_indicador_fazenda_id'), 'alerta_indicador', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_alerta_indicador_fazenda_id'), table_name='alerta_indicador')
    op.drop_index(op.f('ix_alerta_indicador_usuario_id'), table_name='alerta_indicador')
    op.drop_table('alerta_indicador')
