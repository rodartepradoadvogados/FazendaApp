"""vale avulso: tabela de abatimento (permite editar/excluir vale avulso)

Cada `ValeAvulso` (Empreitada/Contrato/Diária) abate diretamente o valor de
parcelas/etapas pendentes ao ser criado — diferente do vale de funcionário,
que tem `ValeParcela` recomputável. Sem um registro de "quanto foi abatido de
qual item", editar ou excluir um vale avulso não tinha como reverter o efeito
de forma exata. Esta tabela grava, por vale, a lista de (item, valor abatido)
para permitir a reversão exata em `atualizar_vale_avulso`/`excluir_vale_avulso`.

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-07-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6c7d8e9f0a1'
down_revision: Union[str, Sequence[str], None] = 'a5b6c7d8e9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'vale_avulso_abatimento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vale_avulso_id', sa.Integer(), nullable=False),
        sa.Column('item_tipo', sa.String(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('valor_abatido', sa.Float(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['vale_avulso_id'], ['vale_avulso.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_vale_avulso_abatimento_vale_avulso_id'), 'vale_avulso_abatimento', ['vale_avulso_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_vale_avulso_abatimento_vale_avulso_id'), table_name='vale_avulso_abatimento')
    op.drop_table('vale_avulso_abatimento')
