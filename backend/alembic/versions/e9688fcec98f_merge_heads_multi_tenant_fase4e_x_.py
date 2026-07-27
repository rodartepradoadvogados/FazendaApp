"""merge heads: multi-tenant fase4e x cobranca/contrato cowdata

Revision ID: e9688fcec98f
Revises: 4b1af857ed36, 557612f98f71
Create Date: 2026-07-27 00:49:35.239100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9688fcec98f'
down_revision: Union[str, Sequence[str], None] = ('4b1af857ed36', '557612f98f71')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
