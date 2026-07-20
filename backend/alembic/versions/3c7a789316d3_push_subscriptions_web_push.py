"""push subscriptions (web push)

Revision ID: 3c7a789316d3
Revises: 6b87f4f6ae02
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '3c7a789316d3'
down_revision: Union[str, Sequence[str], None] = '6b87f4f6ae02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'push_subscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('p256dh', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('auth', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_agent', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_push_subscription_usuario_id'), 'push_subscription', ['usuario_id'], unique=False)
    op.create_index(op.f('ix_push_subscription_endpoint'), 'push_subscription', ['endpoint'], unique=False)

    op.create_table(
        'push_notificacao_enviada',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('chave', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('data_referencia', sa.Date(), nullable=False),
        sa.Column('enviado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_push_notificacao_enviada_usuario_id'), 'push_notificacao_enviada', ['usuario_id'], unique=False)
    op.create_index(op.f('ix_push_notificacao_enviada_chave'), 'push_notificacao_enviada', ['chave'], unique=False)
    op.create_index(op.f('ix_push_notificacao_enviada_data_referencia'), 'push_notificacao_enviada', ['data_referencia'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_push_notificacao_enviada_data_referencia'), table_name='push_notificacao_enviada')
    op.drop_index(op.f('ix_push_notificacao_enviada_chave'), table_name='push_notificacao_enviada')
    op.drop_index(op.f('ix_push_notificacao_enviada_usuario_id'), table_name='push_notificacao_enviada')
    op.drop_table('push_notificacao_enviada')

    op.drop_index(op.f('ix_push_subscription_endpoint'), table_name='push_subscription')
    op.drop_index(op.f('ix_push_subscription_usuario_id'), table_name='push_subscription')
    op.drop_table('push_subscription')
