"""reverter bst nao apta imediatamente

Revision ID: fb04fb74d735
Revises: caa123818572
Create Date: 2026-07-22 01:17:54.378172

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb04fb74d735'
down_revision: Union[str, Sequence[str], None] = 'caa123818572'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('animal', sa.Column(
        'aguardando_nova_aplicacao_bst', sa.Boolean(), nullable=False, server_default=sa.text('false'),
    ))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('animal', 'aguardando_nova_aplicacao_bst')
