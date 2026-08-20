"""categoria_alimento: adiciona categoria_pai_id (subdivisão em dois níveis)

Sessão 2 — categorias de alimento (ex.: Concentrado) passam a poder ter
subcategorias (ex.: Proteico, Energético). Migração ADITIVA, SEM BACKFILL:
`categoria_pai_id` nasce NULL para toda categoria existente, que assim
continua sendo uma raiz — nenhuma categoria de hoje muda de significado.

A unicidade de `nome` também muda de escopo: era (nome, fazenda_id), o que
impediria "Proteico" de existir ao mesmo tempo sob "Concentrado" e sob
"Volumoso". Passa a ser (nome, categoria_pai_id, fazenda_id) — mesmo padrão
de troca de UniqueConstraint já usado em c1d2e3f4a5b6 (tipo/metodo_servico_
reprodutivo), via `op.batch_alter_table` porque SQLite não altera constraint
no lugar.

Revision ID: fd30a36c88cf
Revises: 2e06861217cc
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd30a36c88cf'
down_revision: Union[str, Sequence[str], None] = '2e06861217cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('categoria_alimento', sa.Column('categoria_pai_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('categoria_alimento', schema=None) as batch_op:
        batch_op.create_index(
            op.f('ix_categoria_alimento_categoria_pai_id'), ['categoria_pai_id'], unique=False,
        )
        batch_op.create_foreign_key(
            'fk_categoria_alimento_categoria_pai_id', 'categoria_alimento', ['categoria_pai_id'], ['id'],
        )
        batch_op.drop_constraint('uq_categoria_alimento_nome_fazenda', type_='unique')
        batch_op.create_unique_constraint(
            'uq_categoria_alimento_nome_pai_fazenda', ['nome', 'categoria_pai_id', 'fazenda_id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('categoria_alimento', schema=None) as batch_op:
        batch_op.drop_constraint('uq_categoria_alimento_nome_pai_fazenda', type_='unique')
        batch_op.create_unique_constraint('uq_categoria_alimento_nome_fazenda', ['nome', 'fazenda_id'])
        batch_op.drop_constraint('fk_categoria_alimento_categoria_pai_id', type_='foreignkey')
        batch_op.drop_index(op.f('ix_categoria_alimento_categoria_pai_id'))
    op.drop_column('categoria_alimento', 'categoria_pai_id')
