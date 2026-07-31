"""merge heads apos rebase (vale conta corrente + idempotencia)

Revision ID: 0c6ee077a772
Revises: 8df6afc48295, f4bec264b45f
Create Date: 2026-07-31 10:30:56.249696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c6ee077a772'
down_revision: Union[str, Sequence[str], None] = ('8df6afc48295', 'f4bec264b45f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
