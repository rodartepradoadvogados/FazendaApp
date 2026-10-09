"""estoque: marcador "Produto de leite (venda ao laticínio)"

- `estoque.produto_leite` (boolean, NULLABLE, sem default no banco): o item de estoque que a nota do
  laticínio lança em Financeiro (receita). Base da conta de litros do Resultado por litro / custo por
  litro pela NOTA (a "Venda mensal do leite" passa a ser só reserva para meses sem nota).

ADITIVA, idempotente (coluna já criada pelo `create_all` do boot não aborta o upgrade) e SEM backfill:
nenhum item existente é marcado, desativado ou excluído — quem decide qual item é o leite de venda é o
dono. NULL lê como False. O downgrade remove a coluna (a marcação feita nos itens se perde).

Revision ID: d4a8e1b7c935
Revises: d8b3f6a1c294
Create Date: 2026-10-09 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a8e1b7c935'
down_revision: Union[str, Sequence[str], None] = 'd8b3f6a1c294'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _colunas(insp, tabela):
    return {c['name'] for c in insp.get_columns(tabela)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('estoque') and 'produto_leite' not in _colunas(insp, 'estoque'):
        with op.batch_alter_table('estoque') as batch:
            batch.add_column(sa.Column('produto_leite', sa.Boolean(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('estoque') and 'produto_leite' in _colunas(insp, 'estoque'):
        with op.batch_alter_table('estoque') as batch:
            batch.drop_column('produto_leite')
