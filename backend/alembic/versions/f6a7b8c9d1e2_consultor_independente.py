"""fase 2c: contrato de consultor + fazenda gerenciada + registro importado

Revision ID: f6a7b8c9d1e2
Revises: e5f6a7b8c9d1
Create Date: 2026-07-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d1e2'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'contrato_consultor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('plano', sa.String(), nullable=False),
        sa.Column('limite_fazendas', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('aprovado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('data_fechamento', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['aprovado_por_usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contrato_consultor_usuario_id'), 'contrato_consultor', ['usuario_id'], unique=True)

    op.create_table(
        'fazenda_gerenciada',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('consultor_usuario_id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('produtor', sa.String(), nullable=True),
        sa.Column('cidade', sa.String(), nullable=True),
        sa.Column('uf', sa.String(), nullable=True),
        sa.Column('observacoes', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['consultor_usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fazenda_gerenciada_consultor_usuario_id'), 'fazenda_gerenciada', ['consultor_usuario_id'], unique=False)

    op.create_table(
        'registro_importado',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_gerenciada_id', sa.Integer(), nullable=False),
        sa.Column('categoria', sa.String(), nullable=False),
        sa.Column('data_referencia', sa.Date(), nullable=True),
        sa.Column('dados_json', sa.String(), nullable=False),
        sa.Column('arquivo_origem', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fazenda_gerenciada_id'], ['fazenda_gerenciada.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_registro_importado_fazenda_gerenciada_id'), 'registro_importado', ['fazenda_gerenciada_id'], unique=False)
    op.create_index(op.f('ix_registro_importado_categoria'), 'registro_importado', ['categoria'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_registro_importado_categoria'), table_name='registro_importado')
    op.drop_index(op.f('ix_registro_importado_fazenda_gerenciada_id'), table_name='registro_importado')
    op.drop_table('registro_importado')

    op.drop_index(op.f('ix_fazenda_gerenciada_consultor_usuario_id'), table_name='fazenda_gerenciada')
    op.drop_table('fazenda_gerenciada')

    op.drop_index(op.f('ix_contrato_consultor_usuario_id'), table_name='contrato_consultor')
    op.drop_table('contrato_consultor')
