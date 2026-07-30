"""onboarding_usuario: progresso do checklist de primeiro acesso, por usuário

Ver fazenda/models/onboarding.py e fazenda/api/routers/onboarding.py.

Revision ID: 3e341f91135a
Revises: 99b823147c9f
Create Date: 2026-07-29 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e341f91135a'
down_revision: Union[str, Sequence[str], None] = '99b823147c9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'onboarding_usuario',
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('passos_concluidos', sa.String(), nullable=False),
        sa.Column('dispensado', sa.Boolean(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('usuario_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('onboarding_usuario')
