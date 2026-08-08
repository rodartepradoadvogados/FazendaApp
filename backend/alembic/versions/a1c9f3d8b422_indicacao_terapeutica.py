"""indicacao terapeutica

Vínculo N-para-N entre princípio ativo e doença, com prioridade clínica — ver
fazenda/models/sanidade.py::IndicacaoTerapeutica. Base do "substituto
inteligente de medicamentos": ranking de opções indicadas por doença, usado na
consulta (Sanidade > Curativa > Remédios por doença) e no lançamento (banner
de substituto quando o 1º colocado está sem estoque).

Revision ID: a1c9f3d8b422
Revises: e4e1748b2258
Create Date: 2026-08-01 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a1c9f3d8b422'
down_revision: Union[str, Sequence[str], None] = 'e4e1748b2258'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'indicacao_terapeutica',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('principio_ativo_id', sa.Integer(), nullable=False),
        sa.Column('doenca_id', sa.Integer(), nullable=False),
        sa.Column('prioridade', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['principio_ativo_id'], ['principio_ativo.id']),
        sa.ForeignKeyConstraint(['doenca_id'], ['doenca.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('principio_ativo_id', 'doenca_id', name='uq_indicacao_principio_doenca'),
    )
    op.create_index(op.f('ix_indicacao_terapeutica_principio_ativo_id'), 'indicacao_terapeutica', ['principio_ativo_id'])
    op.create_index(op.f('ix_indicacao_terapeutica_doenca_id'), 'indicacao_terapeutica', ['doenca_id'])
    op.create_index(op.f('ix_indicacao_terapeutica_fazenda_id'), 'indicacao_terapeutica', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_indicacao_terapeutica_fazenda_id'), table_name='indicacao_terapeutica')
    op.drop_index(op.f('ix_indicacao_terapeutica_doenca_id'), table_name='indicacao_terapeutica')
    op.drop_index(op.f('ix_indicacao_terapeutica_principio_ativo_id'), table_name='indicacao_terapeutica')
    op.drop_table('indicacao_terapeutica')
