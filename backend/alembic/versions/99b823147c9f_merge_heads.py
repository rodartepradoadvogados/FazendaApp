"""merge heads

Revision ID: 99b823147c9f
Revises: 06f55bae449e, c3d4e5f6a7b8
Create Date: 2026-07-29 15:14:27.080575

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99b823147c9f'
down_revision: Union[str, Sequence[str], None] = ('06f55bae449e', 'c3d4e5f6a7b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
