"""filtro_salvo: conjunto de filtros nomeado pelo usuário, reaplicável nas
telas de relatório (ex.: Financeiro > Extrato completo)

Ver fazenda/models/filtro_salvo.py e fazenda/api/routers/filtros_salvos.py.

Revision ID: 029dcd895d43
Revises: 99b823147c9f
Create Date: 2026-07-29 20:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '029dcd895d43'
down_revision: Union[str, Sequence[str], None] = '99b823147c9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'filtro_salvo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('tela', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('filtros', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_filtro_salvo_usuario_id'), 'filtro_salvo', ['usuario_id'])
    op.create_index(op.f('ix_filtro_salvo_fazenda_id'), 'filtro_salvo', ['fazenda_id'])
    op.create_index(op.f('ix_filtro_salvo_tela'), 'filtro_salvo', ['tela'])
    op.create_index(
        'uq_filtro_salvo_usuario_tela_nome', 'filtro_salvo', ['usuario_id', 'tela', 'nome'], unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_filtro_salvo_usuario_tela_nome', table_name='filtro_salvo')
    op.drop_index(op.f('ix_filtro_salvo_tela'), table_name='filtro_salvo')
    op.drop_index(op.f('ix_filtro_salvo_fazenda_id'), table_name='filtro_salvo')
    op.drop_index(op.f('ix_filtro_salvo_usuario_id'), table_name='filtro_salvo')
    op.drop_table('filtro_salvo')
