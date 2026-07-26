"""merge heads: fase4b rh_folha fazenda_id + lote criterios/pessoa dados civis

Revision ID: d00c11395f94
Revises: a1b2c3d4e5f6, d0a1b2c3d4e5
Create Date: 2026-07-26 15:58:03.800254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd00c11395f94'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'd0a1b2c3d4e5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
