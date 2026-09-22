"""bst pendente inducao lactacao

Revision ID: 01ce25ba18bc
Revises: 9a1d7c5e2b48
Create Date: 2026-09-21 08:34:18.556600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01ce25ba18bc'
down_revision: Union[str, Sequence[str], None] = '9a1d7c5e2b48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('animal', sa.Column(
        'bst_pendente_inducao_lactacao', sa.Boolean(), nullable=False, server_default=sa.text('false'),
    ))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('animal', 'bst_pendente_inducao_lactacao')
