"""vinculo financeiro sanitario reprodutivo

Revision ID: a3f7c9d1e246
Revises: 173998be20ea
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a3f7c9d1e246'
down_revision: Union[str, Sequence[str], None] = '173998be20ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('plano_conta_gerencial', sa.Column('pede_vinculo_sanitario_reprodutivo', sa.Boolean(), nullable=True))
    op.add_column('sanidade', sa.Column('numero_lancamento_vinculado', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f('ix_sanidade_numero_lancamento_vinculado'), 'sanidade', ['numero_lancamento_vinculado'], unique=False)
    op.add_column('exame_resultado', sa.Column('numero_lancamento_vinculado', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f('ix_exame_resultado_numero_lancamento_vinculado'), 'exame_resultado', ['numero_lancamento_vinculado'], unique=False)
    op.add_column('servico', sa.Column('numero_lancamento_vinculado', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f('ix_servico_numero_lancamento_vinculado'), 'servico', ['numero_lancamento_vinculado'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_servico_numero_lancamento_vinculado'), table_name='servico')
    op.drop_column('servico', 'numero_lancamento_vinculado')
    op.drop_index(op.f('ix_exame_resultado_numero_lancamento_vinculado'), table_name='exame_resultado')
    op.drop_column('exame_resultado', 'numero_lancamento_vinculado')
    op.drop_index(op.f('ix_sanidade_numero_lancamento_vinculado'), table_name='sanidade')
    op.drop_column('sanidade', 'numero_lancamento_vinculado')
    op.drop_column('plano_conta_gerencial', 'pede_vinculo_sanitario_reprodutivo')
