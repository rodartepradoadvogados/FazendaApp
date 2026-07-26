"""pessoa: dados civis (RG, data nascimento, gênero, estado civil) e endereço estruturado

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-07-25 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'b6c7d8e9f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('pessoa', sa.Column('rg', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('data_nascimento', sa.Date(), nullable=True))
    op.add_column('pessoa', sa.Column('genero', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('estado_civil', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('endereco_rua', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('endereco_numero', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('endereco_bairro', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('endereco_cidade', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('endereco_uf', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pessoa', 'endereco_uf')
    op.drop_column('pessoa', 'endereco_cidade')
    op.drop_column('pessoa', 'endereco_bairro')
    op.drop_column('pessoa', 'endereco_numero')
    op.drop_column('pessoa', 'endereco_rua')
    op.drop_column('pessoa', 'estado_civil')
    op.drop_column('pessoa', 'genero')
    op.drop_column('pessoa', 'data_nascimento')
    op.drop_column('pessoa', 'rg')
