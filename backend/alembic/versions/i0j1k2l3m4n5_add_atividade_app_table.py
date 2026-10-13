"""add_atividade_app_table

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'i0j1k2l3m4n5'
down_revision = 'h9i0j1k2l3m4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    # Create atividade_app table
    if not insp.has_table('atividade_app'):
        op.create_table(
            'atividade_app',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('canal', sa.String(length=10), nullable=False),  # 'app' | 'pwa' | 'web'
            sa.Column('evento', sa.String(length=20), nullable=False),  # 'aberto' | 'primeiro_plano' | 'segundo_plano' | 'batimento'
            sa.Column('app_versao', sa.String(length=20), nullable=True),
            sa.Column('device_id', sa.String(length=100), nullable=True),
            sa.Column('ocorrido_em', sa.DateTime(), nullable=False),  # timestamp do cliente
            sa.Column('recebido_em', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),  # timestamp do servidor
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_atividade_app_usuario_id'), 'atividade_app', ['usuario_id'], unique=False)
        op.create_index(op.f('ix_atividade_app_fazenda_id'), 'atividade_app', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_atividade_app_recebido_em'), 'atividade_app', ['recebido_em'], unique=False)
        op.create_index(op.f('ix_atividade_app_ocorrido_em'), 'atividade_app', ['ocorrido_em'], unique=False)
        # Índice composto para dedupe: mesmo usuário + canal + evento em < 60s
        op.create_index(op.f('ix_atividade_app_dedupe'), 'atividade_app', ['usuario_id', 'canal', 'evento', 'recebido_em'], unique=False)
    
    # Add ultimo_acesso column to usuario table
    if insp.has_table('usuario'):
        cols = [c['name'] for c in insp.get_columns('usuario')]
        if 'ultimo_acesso' not in cols:
            op.add_column('usuario', sa.Column('ultimo_acesso', sa.DateTime(), nullable=True))
            op.create_index(op.f('ix_usuario_ultimo_acesso'), 'usuario', ['ultimo_acesso'], unique=False)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    
    # Remove ultimo_acesso from usuario
    if insp.has_table('usuario'):
        cols = [c['name'] for c in insp.get_columns('usuario')]
        if 'ultimo_acesso' in cols:
            op.drop_index(op.f('ix_usuario_ultimo_acesso'), table_name='usuario')
            op.drop_column('usuario', 'ultimo_acesso')
    
    # Drop atividade_app table
    if insp.has_table('atividade_app'):
        op.drop_index(op.f('ix_atividade_app_dedupe'), table_name='atividade_app')
        op.drop_index(op.f('ix_atividade_app_ocorrido_em'), table_name='atividade_app')
        op.drop_index(op.f('ix_atividade_app_recebido_em'), table_name='atividade_app')
        op.drop_index(op.f('ix_atividade_app_fazenda_id'), table_name='atividade_app')
        op.drop_index(op.f('ix_atividade_app_usuario_id'), table_name='atividade_app')
        op.drop_table('atividade_app')