"""permissao_equipe_cowdata: login/permissões de membro da Equipe CowData no Painel CowData

Revision ID: 260219cd5331
Revises: 097a04cc68da
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '260219cd5331'
down_revision: Union[str, Sequence[str], None] = '097a04cc68da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'permissao_equipe_cowdata',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('areas', sa.String(), nullable=False),
        sa.Column('pode_suspender_assinatura', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('pode_acessar_fazendas', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('pode_alterar_cadastro', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('pode_modificar_suspender_plano', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('pode_emitir_auditar_contratos', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('pode_emitir_cobrancas', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('pode_vincular_usuarios', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('pode_cadastrar_usuarios', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('usuario_id'),
    )
    op.create_index(op.f('ix_permissao_equipe_cowdata_usuario_id'), 'permissao_equipe_cowdata', ['usuario_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('permissao_equipe_cowdata')
