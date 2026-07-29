"""push_token_fcm: token de push do app Android nativo (Firebase Cloud Messaging)

Canal irmão de push_subscription (Web Push do navegador/PWA) — o app
Android nativo (Capacitor) usa FCM em vez de Web Push, que não é confiável
dentro da WebView com o app fechado. Ver fazenda/rules/fcm.py e
fazenda/api/routers/push.py.

Revision ID: 06f55bae449e
Revises: af747b759cc0
Create Date: 2026-07-29 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06f55bae449e'
down_revision: Union[str, Sequence[str], None] = 'af747b759cc0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'push_token_fcm',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('plataforma', sa.String(), nullable=False, server_default='android'),
        sa.Column('modelo', sa.String(), nullable=True),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_push_token_fcm_usuario_id'), 'push_token_fcm', ['usuario_id'])
    op.create_index(op.f('ix_push_token_fcm_token'), 'push_token_fcm', ['token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_push_token_fcm_token'), table_name='push_token_fcm')
    op.drop_index(op.f('ix_push_token_fcm_usuario_id'), table_name='push_token_fcm')
    op.drop_table('push_token_fcm')
