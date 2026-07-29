"""assistente_ensinamento: base de conhecimento do dono para o Assistente

Tabela nova (aditiva) — texto livre cadastrado pelo dono, concatenado ao
SYSTEM_PROMPT do Assistente Virtual a cada pergunta (ver
fazenda/rules/assistente.py). Isolada por fazenda_id, mesmo padrão de
sugestao_manual_fazenda/portal_mensagem.

Revision ID: c3d4e5f6a7b8
Revises: d1e2f3a4b5c6
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'assistente_ensinamento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('titulo', sa.String(), nullable=False),
        sa.Column('texto', sa.String(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_assistente_ensinamento_fazenda_id'), 'assistente_ensinamento', ['fazenda_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_assistente_ensinamento_fazenda_id'), table_name='assistente_ensinamento')
    op.drop_table('assistente_ensinamento')
