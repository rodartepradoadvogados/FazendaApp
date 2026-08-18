"""movimento_estoque: valor_unitario (preço no momento do movimento, pro custo físico do RMCA)

O custo físico do RMCA (rules/rmca.py::calcular_custo_fisico) multiplicava
TODO o histórico de consumo pelo preço ATUAL do item — sem um snapshot do
preço em cada MovimentoEstoque, reescrevia retroativamente o custo de meses
cujo preço já mudou. Esta coluna grava o `Estoque.valor_unitario` de quando
o movimento foi lançado; movimentos antigos ficam None (a leitura cai no
preço atual como aproximação, comportamento de sempre).

Coluna aditiva e nula: nenhum registro existente muda de comportamento.

Revision ID: eb68f8993eb9
Revises: 52e4041d41d7
Create Date: 2026-08-18 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb68f8993eb9'
down_revision: Union[str, Sequence[str], None] = '52e4041d41d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('movimento_estoque', sa.Column('valor_unitario', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('movimento_estoque', 'valor_unitario')
