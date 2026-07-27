"""merge heads: fazenda tipo_documento/cep x alimentacao_estado fazenda_id

Revision ID: 4e6ea12a6656
Revises: 3ec7d263d10f, a3f9c1e2d4b6
Create Date: 2026-07-27 06:44:47.681904

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e6ea12a6656'
down_revision: Union[str, Sequence[str], None] = ('3ec7d263d10f', 'a3f9c1e2d4b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
