"""Manual da Fazenda: parametro_manual_fazenda + sugestao_manual_fazenda

Rotina automática + insights + sugestões customizáveis (ver
fazenda/rules/manual_fazenda.py e routers/manual_fazenda.py).

Revision ID: f920fe52a55b
Revises: d4c7a4de4f1e
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f920fe52a55b'
down_revision: Union[str, Sequence[str], None] = 'd4c7a4de4f1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'parametro_manual_fazenda',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_semanal_ativo', sa.Boolean(), nullable=False),
        sa.Column('ultimo_envio_semanal_em', sa.DateTime(), nullable=True),
        sa.Column('responsavel_manejo_nome', sa.String(), nullable=True),
        sa.Column('responsavel_manejo_empresa', sa.String(), nullable=True),
        sa.Column('tem_contrato_manejo', sa.Boolean(), nullable=False),
        sa.Column('contrato_manejo_arquivo_nome', sa.String(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_parametro_manual_fazenda_fazenda_id'), 'parametro_manual_fazenda', ['fazenda_id'], unique=False)

    op.create_table(
        'sugestao_manual_fazenda',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('texto', sa.String(), nullable=False),
        sa.Column('categoria', sa.String(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('ordem', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sugestao_manual_fazenda_fazenda_id'), 'sugestao_manual_fazenda', ['fazenda_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sugestao_manual_fazenda_fazenda_id'), table_name='sugestao_manual_fazenda')
    op.drop_table('sugestao_manual_fazenda')
    op.drop_index(op.f('ix_parametro_manual_fazenda_fazenda_id'), table_name='parametro_manual_fazenda')
    op.drop_table('parametro_manual_fazenda')
