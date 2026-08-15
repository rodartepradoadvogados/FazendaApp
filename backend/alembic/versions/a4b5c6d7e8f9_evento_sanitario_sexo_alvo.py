"""evento_sanitario_sexo_alvo

Revision ID: a4b5c6d7e8f9
Revises: e748031820d9
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'e748031820d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("evento_sanitario", sa.Column("sexo_alvo", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("evento_sanitario", "sexo_alvo")
