"""evento_sanitario_servico_financeiro

Revision ID: e748031820d9
Revises: 846407c16c09
Create Date: 2026-08-02 21:59:26.332895

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e748031820d9'
down_revision: Union[str, Sequence[str], None] = '846407c16c09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("evento_sanitario", sa.Column("servico_financeiro", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("evento_sanitario", "servico_financeiro")
