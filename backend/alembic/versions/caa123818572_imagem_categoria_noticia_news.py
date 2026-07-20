"""imagem e categoria em noticia_news

Revision ID: caa123818572
Revises: b128c3e68913
Create Date: 2026-07-20 14:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'caa123818572'
down_revision: Union[str, Sequence[str], None] = 'b128c3e68913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('noticia_news', sa.Column('imagem', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('noticia_news', sa.Column('categoria', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('noticia_news', 'categoria')
    op.drop_column('noticia_news', 'imagem')
