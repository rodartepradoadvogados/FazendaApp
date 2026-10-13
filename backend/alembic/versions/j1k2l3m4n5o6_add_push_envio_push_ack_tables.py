"""add_push_envio_push_ack_tables

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'j1k2l3m4n5o6'
down_revision = 'i0j1k2l3m4n5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    # Create push_envio table (auditoria de envio)
    if not insp.has_table('push_envio'):
        op.create_table(
            'push_envio',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('push_token_id', sa.Integer(), nullable=True),
            sa.Column('canal', sa.String(length=10), nullable=False),  # 'fcm' | 'webpush'
            sa.Column('categoria', sa.String(length=50), nullable=True),
            sa.Column('titulo', sa.String(length=200), nullable=True),
            sa.Column('corpo', sa.Text(), nullable=True),
            sa.Column('dados', sa.Text(), nullable=True),  # JSON payload completo
            sa.Column('enviado_em', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('resultado', sa.String(length=20), nullable=False),  # 'ok' | 'token_invalido' | 'erro'
            sa.Column('fcm_message_id', sa.String(length=100), nullable=True),
            sa.Column('erro_curto', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['push_token_id'], ['push_token_fcm.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_push_envio_usuario_id'), 'push_envio', ['usuario_id'], unique=False)
        op.create_index(op.f('ix_push_envio_enviado_em'), 'push_envio', ['enviado_em'], unique=False)
        op.create_index(op.f('ix_push_envio_resultado'), 'push_envio', ['resultado'], unique=False)
    
    # Create push_ack table (confirmação de recebimento)
    if not insp.has_table('push_ack'):
        op.create_table(
            'push_ack',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('push_envio_id', sa.Integer(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('token_fcm', sa.String(length=200), nullable=True),
            sa.Column('estado_app', sa.String(length=20), nullable=False),  # 'primeiro_plano' | 'segundo_plano' | 'tocada'
            sa.Column('recebido_em', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['push_envio_id'], ['push_envio.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_push_ack_push_envio_id'), 'push_ack', ['push_envio_id'], unique=False)
        op.create_index(op.f('ix_push_ack_usuario_id'), 'push_ack', ['usuario_id'], unique=False)
        op.create_index(op.f('ix_push_ack_recebido_em'), 'push_ack', ['recebido_em'], unique=False)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    if insp.has_table('push_ack'):
        op.drop_index(op.f('ix_push_ack_recebido_em'), table_name='push_ack')
        op.drop_index(op.f('ix_push_ack_usuario_id'), table_name='push_ack')
        op.drop_index(op.f('ix_push_ack_push_envio_id'), table_name='push_ack')
        op.drop_table('push_ack')
    
    if insp.has_table('push_envio'):
        op.drop_index(op.f('ix_push_envio_resultado'), table_name='push_envio')
        op.drop_index(op.f('ix_push_envio_enviado_em'), table_name='push_envio')
        op.drop_index(op.f('ix_push_envio_usuario_id'), table_name='push_envio')
        op.drop_table('push_envio')