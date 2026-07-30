"""merge heads

Revision ID: cca93113e796
Revises: 22fd9109e69a, 8132798801c0, e1b3e2dec237, e93e3302df29
Create Date: 2026-07-30 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cca93113e796'
down_revision: Union[str, Sequence[str], None] = ('22fd9109e69a', '8132798801c0', 'e1b3e2dec237', 'e93e3302df29')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
