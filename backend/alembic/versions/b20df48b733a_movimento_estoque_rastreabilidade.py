"""movimento_estoque: rastreabilidade (estoque_id, origem_tipo, origem_id)

Ponto único de baixa/devolução de estoque (fazenda.rules.estoque_baixa) —
até aqui o vínculo de MovimentoEstoque com o item era só o TEXTO `nome_item`,
que quebra se o item for renomeado. Adiciona o vínculo relacional
(`estoque_id`) e de onde veio o movimento (`origem_tipo`/`origem_id`), com
backfill best-effort de `estoque_id` casando `nome_item` com `Estoque.nome`
dentro da mesma fazenda.

Revision ID: b20df48b733a
Revises: cca93113e796
Create Date: 2026-07-30 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b20df48b733a'
down_revision: Union[str, Sequence[str], None] = 'cca93113e796'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('movimento_estoque', sa.Column('estoque_id', sa.Integer(), nullable=True))
    op.add_column('movimento_estoque', sa.Column('origem_tipo', sa.String(), nullable=True))
    op.add_column('movimento_estoque', sa.Column('origem_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_movimento_estoque_estoque_id'), 'movimento_estoque', ['estoque_id'])
    with op.batch_alter_table('movimento_estoque') as batch_op:
        batch_op.create_foreign_key(
            'fk_movimento_estoque_estoque_id', 'estoque', ['estoque_id'], ['id'],
        )

    # Backfill best-effort: casa nome_item com Estoque.nome dentro da mesma
    # fazenda (ou sem fazenda, quando nenhum dos dois lados tem fazenda_id) —
    # movimentos cujo nome não bate com item nenhum (item renomeado/excluído
    # depois) ficam com estoque_id NULL, sem quebrar nada.
    op.execute(
        """
        UPDATE movimento_estoque
        SET estoque_id = (
            SELECT e.id FROM estoque e
            WHERE e.nome = movimento_estoque.nome_item
              AND (
                    (movimento_estoque.fazenda_id IS NULL AND e.fazenda_id IS NULL)
                    OR e.fazenda_id = movimento_estoque.fazenda_id
                  )
            LIMIT 1
        )
        WHERE estoque_id IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('movimento_estoque') as batch_op:
        batch_op.drop_constraint('fk_movimento_estoque_estoque_id', type_='foreignkey')
    op.drop_index(op.f('ix_movimento_estoque_estoque_id'), table_name='movimento_estoque')
    op.drop_column('movimento_estoque', 'origem_id')
    op.drop_column('movimento_estoque', 'origem_tipo')
    op.drop_column('movimento_estoque', 'estoque_id')
