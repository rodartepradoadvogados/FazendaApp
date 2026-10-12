"""add_conteudo_to_documento_arquivado

Revision ID: c3d4e5f6a7b8
Revises: 78dbbd8c8c0f
Create Date: 2026-10-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = '78dbbd8c8c0f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    # Add conteudo column to documento_arquivado
    if insp.has_table('documento_arquivado'):
        if 'conteudo' not in [c['name'] for c in insp.get_columns('documento_arquivado')]:
            op.add_column('documento_arquivado', sa.Column('conteudo', sa.LargeBinary(), nullable=True))
        
        # Make caminho_storage nullable
        if 'caminho_storage' in [c['name'] for c in insp.get_columns('documento_arquivado')]:
            op.alter_column('documento_arquivado', 'caminho_storage',
                           existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    if insp.has_table('documento_arquivado'):
        if 'conteudo' in [c['name'] for c in insp.get_columns('documento_arquivado')]:
            op.drop_column('documento_arquivado', 'conteudo')
        
        # Make caminho_storage non-nullable again
        if 'caminho_storage' in [c['name'] for c in insp.get_columns('documento_arquivado')]:
            op.alter_column('documento_arquivado', 'caminho_storage',
                           existing_type=sa.String(), nullable=False)