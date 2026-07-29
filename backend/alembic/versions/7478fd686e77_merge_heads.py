"""merge heads

Revision ID: 7478fd686e77
Revises: 367724c4f608, 99b823147c9f
Create Date: 2026-07-29 20:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7478fd686e77'
down_revision: Union[str, Sequence[str], None] = ('367724c4f608', '99b823147c9f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
