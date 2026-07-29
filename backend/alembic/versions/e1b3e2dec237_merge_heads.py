"""merge heads

Revision ID: e1b3e2dec237
Revises: 029dcd895d43, 7478fd686e77
Create Date: 2026-07-29 18:32:32.717612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1b3e2dec237'
down_revision: Union[str, Sequence[str], None] = ('029dcd895d43', '7478fd686e77')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
