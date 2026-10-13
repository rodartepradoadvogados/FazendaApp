"""merge: preco_plano + retencao_90d

Revision ID: b3ada7760c6e
Revises: b8c9d0e1f2a3, k2l3m4n5o6p7
Create Date: 2026-10-13 06:02:17.057761

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3ada7760c6e'
down_revision: Union[str, Sequence[str], None] = ('b8c9d0e1f2a3', 'k2l3m4n5o6p7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
