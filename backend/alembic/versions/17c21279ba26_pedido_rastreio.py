"""pedido: enviado, codigo_rastreio, link_rastreio

Quando o status manual de um Pedido vira "parcialmente_atendido", a tela
pergunta se o pedido já foi enviado — se sim, oferece guardar o código de
rastreio e o link de acompanhamento (ver PUT /pedidos/{id}/rastreio).

Colunas aditivas e nulas: nenhum pedido existente muda de comportamento.

Revision ID: 17c21279ba26
Revises: d5e6f7a8b9c0
Create Date: 2026-08-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17c21279ba26'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pedido', sa.Column('enviado', sa.Boolean(), nullable=True))
    op.add_column('pedido', sa.Column('codigo_rastreio', sa.String(), nullable=True))
    op.add_column('pedido', sa.Column('link_rastreio', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('pedido', 'link_rastreio')
    op.drop_column('pedido', 'codigo_rastreio')
    op.drop_column('pedido', 'enviado')
