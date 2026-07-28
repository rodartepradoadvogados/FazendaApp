"""merge heads sistema fazenda_id e documento/chamado

Revision ID: 0738880aaec2
Revises: c9d0e1f2a3b4, f2a3b4c5d6e7
Create Date: 2026-07-28 18:55:31.690189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0738880aaec2'
down_revision: Union[str, Sequence[str], None] = ('c9d0e1f2a3b4', 'f2a3b4c5d6e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
