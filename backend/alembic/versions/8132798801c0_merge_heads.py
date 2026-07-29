"""merge heads

Revision ID: 8132798801c0
Revises: 029dcd895d43, 7478fd686e77, 3e341f91135a
Create Date: 2026-07-29 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8132798801c0'
down_revision: Union[str, Sequence[str], None] = ('029dcd895d43', '7478fd686e77', '3e341f91135a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
