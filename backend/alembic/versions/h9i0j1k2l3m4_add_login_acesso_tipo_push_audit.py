"""add_login_acesso_tipo_push_audit

Revision ID: h9i0j1k2l3m4
Revises: f6a7b8c9d0e1
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'h9i0j1k2l3m4'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    # Add tipo and detalhes columns to login_acesso
    if insp.has_table('login_acesso'):
        cols = [c['name'] for c in insp.get_columns('login_acesso')]
        if 'tipo' not in cols:
            op.add_column('login_acesso', sa.Column('tipo', sa.String(), nullable=False, server_default='senha'))
            op.create_index(op.f('ix_login_acesso_tipo'), 'login_acesso', ['tipo'], unique=False)
        if 'detalhes' not in cols:
            op.add_column('login_acesso', sa.Column('detalhes', sa.Text(), nullable=True))
    
    # Create push_notificacao_recebida table
    if not insp.has_table('push_notificacao_recebida'):
        op.create_table(
            'push_notificacao_recebida',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('push_token_id', sa.Integer(), nullable=True),
            sa.Column('titulo', sa.String(), nullable=True),
            sa.Column('corpo', sa.String(), nullable=True),
            sa.Column('dados', sa.Text(), nullable=True),
            sa.Column('recebido_em', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('estado_app', sa.String(), nullable=True),
            sa.Column('token_fcm', sa.String(), nullable=True),
            sa.ForeignKeyConstraint(['push_token_id'], ['push_token_fcm.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_push_notificacao_recebida_usuario_id'), 'push_notificacao_recebida', ['usuario_id'], unique=False)
        op.create_index(op.f('ix_push_notificacao_recebida_push_token_id'), 'push_notificacao_recebida', ['push_token_id'], unique=False)
        op.create_index(op.f('ix_push_notificacao_recebida_recebido_em'), 'push_notificacao_recebida', ['recebido_em'], unique=False)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    # Drop push_notificacao_recebida table
    if insp.has_table('push_notificacao_recebida'):
        op.drop_index(op.f('ix_push_notificacao_recebida_recebido_em'), table_name='push_notificacao_recebida')
        op.drop_index(op.f('ix_push_notificacao_recebida_push_token_id'), table_name='push_notificacao_recebida')
        op.drop_index(op.f('ix_push_notificacao_recebida_usuario_id'), table_name='push_notificacao_recebida')
        op.drop_table('push_notificacao_recebida')
    
    # Remove columns from login_acesso
    if insp.has_table('login_acesso'):
        cols = [c['name'] for c in insp.get_columns('login_acesso')]
        if 'detalhes' in cols:
            op.drop_column('login_acesso', 'detalhes')
        if 'tipo' in cols:
            op.drop_index(op.f('ix_login_acesso_tipo'), table_name='login_acesso')
            op.drop_column('login_acesso', 'tipo')