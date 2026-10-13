"""add_conteudo_to_documento_arquivado

Revision ID: f6a7b8c9d0e1
Revises: 78dbbd8c8c0f
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'g7h8i9j0k1l2'
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
            # batch_alter_table: SQLite não suporta ALTER COLUMN direto.
            with op.batch_alter_table('documento_arquivado') as batch:
                batch.alter_column('caminho_storage', existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    if insp.has_table('documento_arquivado'):
        if 'conteudo' in [c['name'] for c in insp.get_columns('documento_arquivado')]:
            op.drop_column('documento_arquivado', 'conteudo')
        
        # Make caminho_storage non-nullable again
        if 'caminho_storage' in [c['name'] for c in insp.get_columns('documento_arquivado')]:
            with op.batch_alter_table('documento_arquivado') as batch:
                batch.alter_column('caminho_storage', existing_type=sa.String(), nullable=False)