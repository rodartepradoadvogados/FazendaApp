"""lote: novos critérios (situação reprodutiva, dias gestação/desde serviço) e vínculo com categoria de manejo

Revision ID: d0a1b2c3d4e5
Revises: c9e0f1a2b3c4
Create Date: 2026-07-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'c9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('lote', sa.Column('situacao_reprodutiva', sa.String(), nullable=True))
    op.add_column('lote', sa.Column('dias_gestacao_min', sa.Integer(), nullable=True))
    op.add_column('lote', sa.Column('dias_gestacao_max', sa.Integer(), nullable=True))
    op.add_column('lote', sa.Column('dias_desde_servico_min', sa.Integer(), nullable=True))
    op.add_column('lote', sa.Column('dias_desde_servico_max', sa.Integer(), nullable=True))
    op.add_column('lote', sa.Column('categoria_manejo_ids', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('lote', 'categoria_manejo_ids')
    op.drop_column('lote', 'dias_desde_servico_max')
    op.drop_column('lote', 'dias_desde_servico_min')
    op.drop_column('lote', 'dias_gestacao_max')
    op.drop_column('lote', 'dias_gestacao_min')
    op.drop_column('lote', 'situacao_reprodutiva')
