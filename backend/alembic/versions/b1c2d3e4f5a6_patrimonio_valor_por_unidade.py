"""patrimonio_valor_por_unidade

Revision ID: b1c2d3e4f5a6
Revises: 3bd371891acd
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '3bd371891acd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # False preserva o comportamento de todo item já cadastrado: valor_total
    # já é o valor do lote inteiro (ver Patrimonio.valor_por_unidade e
    # rules.patrimonio.valor_base_aquisicao) — nenhum dado existente muda de
    # valor com esta migração, só passa a existir a opção de marcar
    # "valor_total é por unidade" em itens novos/editados.
    op.add_column("patrimonio", sa.Column("valor_por_unidade", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("patrimonio") as batch_op:
        batch_op.alter_column("valor_por_unidade", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("patrimonio", "valor_por_unidade")
