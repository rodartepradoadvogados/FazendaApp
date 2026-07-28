"""merge heads manual_fazenda e usuario_fazenda_contador

Revision ID: 81ad18d4e7a9
Revises: e1f2a3b4c5d6, f920fe52a55b
Create Date: 2026-07-28 12:13:22.031723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '81ad18d4e7a9'
down_revision: Union[str, Sequence[str], None] = ('e1f2a3b4c5d6', 'f920fe52a55b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
