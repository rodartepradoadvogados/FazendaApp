"""origem perda prenhez

Revision ID: 810153450ce9
Revises: 8562e8574399
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '810153450ce9'
down_revision: Union[str, Sequence[str], None] = '8562e8574399'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('servico', sa.Column('origem_perda_prenhez', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('servico', 'origem_perda_prenhez')
