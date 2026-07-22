"""reset senha usuario

Revision ID: 173998be20ea
Revises: fb04fb74d735
Create Date: 2026-07-22 02:18:46.918998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '173998be20ea'
down_revision: Union[str, Sequence[str], None] = 'fb04fb74d735'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usuario', sa.Column('reset_senha_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('usuario', sa.Column('reset_senha_expira', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_usuario_reset_senha_token'), 'usuario', ['reset_senha_token'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_usuario_reset_senha_token'), table_name='usuario')
    op.drop_column('usuario', 'reset_senha_expira')
    op.drop_column('usuario', 'reset_senha_token')
