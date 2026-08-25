"""pedido_item: quantidade_entregue

Fundação do novo ciclo de vida de Pedidos (Peça 1/5). Hoje o status do
Pedido é derivado de `quantidade_atendida`/`valor_atendido`, que só mudam
quando um lançamento financeiro ou um movimento de estoque é vinculado ao
item — ou seja, dá pra marcar "Atendido" sem nada ter sido fisicamente
entregue. `quantidade_entregue` é um contador PARALELO e independente:
só será escrito por uma ação explícita de "marcar entrega" (próxima peça),
nunca por dinheiro lançado ou estoque baixado. A função pura que calcula o
status a partir dela (`fazenda.rules.pedido_status.calcular_status_pedido`)
já existe nesta peça, mas nenhum router ainda a chama — `quantidade_atendida`
continua sendo o que dirige o status hoje.

Revision ID: 0bfa9fbc2926
Revises: e4e7f4108c13
Create Date: 2026-08-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0bfa9fbc2926'
down_revision: Union[str, Sequence[str], None] = 'e4e7f4108c13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'pedido_item',
        sa.Column('quantidade_entregue', sa.Float(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pedido_item', 'quantidade_entregue')
