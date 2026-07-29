"""merge heads

Revision ID: 22fd9109e69a
Revises: 029dcd895d43, 7478fd686e77, f8021c7a8c19
Create Date: 2026-07-29 21:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22fd9109e69a'
down_revision: Union[str, Sequence[str], None] = ('029dcd895d43', '7478fd686e77', 'f8021c7a8c19')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
