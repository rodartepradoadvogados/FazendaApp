"""patrimonio_valor_mercado_e_vinculo

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-04 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, Sequence[str], None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("estoque", sa.Column("gera_patrimonio", sa.Boolean(), nullable=True))

    op.add_column("patrimonio", sa.Column("depreciavel", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("patrimonio", sa.Column("valor_mercado_atual", sa.Float(), nullable=True))
    op.add_column("patrimonio", sa.Column("data_ultima_atualizacao_valor_mercado", sa.Date(), nullable=True))
    op.add_column("patrimonio", sa.Column("atualizacao_valor_mercado_frequencia_meses", sa.Integer(), nullable=True))
    with op.batch_alter_table("patrimonio") as batch_op:
        batch_op.alter_column("depreciavel", server_default=None)

    op.add_column("conta_gerencial", sa.Column("patrimonio_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_conta_gerencial_patrimonio_id"), "conta_gerencial", ["patrimonio_id"], unique=False)
    with op.batch_alter_table("conta_gerencial") as batch_op:
        batch_op.create_foreign_key("fk_conta_gerencial_patrimonio_id", "patrimonio", ["patrimonio_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("conta_gerencial") as batch_op:
        batch_op.drop_constraint("fk_conta_gerencial_patrimonio_id", type_="foreignkey")
    op.drop_index(op.f("ix_conta_gerencial_patrimonio_id"), table_name="conta_gerencial")
    op.drop_column("conta_gerencial", "patrimonio_id")

    op.drop_column("patrimonio", "atualizacao_valor_mercado_frequencia_meses")
    op.drop_column("patrimonio", "data_ultima_atualizacao_valor_mercado")
    op.drop_column("patrimonio", "valor_mercado_atual")
    op.drop_column("patrimonio", "depreciavel")

    op.drop_column("estoque", "gera_patrimonio")
