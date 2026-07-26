"""merge heads: fase4e alimentacao/producao/recria fazenda_id

Revision ID: 4b1af857ed36
Revises: c1d2e3f4a5c8, c2d3e4f5a6c9, c3d4e5f6a7ca
Create Date: 2026-07-26 18:39:43.492535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b1af857ed36'
down_revision: Union[str, Sequence[str], None] = ('c1d2e3f4a5c8', 'c2d3e4f5a6c9', 'c3d4e5f6a7ca')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
