"""add_usuarios_auditados_to_usuario

Revision ID: g7h8i9j0k1l2
Revises: 78dbbd8c8c0f
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'g7h8i9j0k1l2'
down_revision = '78dbbd8c8c0f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    # Add usuarios_auditados column to usuario
    if insp.has_table('usuario'):
        if 'usuarios_auditados' not in [c['name'] for c in insp.get_columns('usuario')]:
            op.add_column('usuario', sa.Column('usuarios_auditados', sa.Text(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    if insp.has_table('usuario'):
        if 'usuarios_auditados' in [c['name'] for c in insp.get_columns('usuario')]:
            op.drop_column('usuario', 'usuarios_auditados')