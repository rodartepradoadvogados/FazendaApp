"""cadastros_estoque

Revision ID: 56fb4f344643
Revises: a29c96161bed
Create Date: 2026-08-04 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56fb4f344643'
down_revision: Union[str, Sequence[str], None] = 'a29c96161bed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABELAS = [
    "local_armazenamento",
    "categoria_estoque",
    "finalidade_estoque",
    "unidade_estoque",
    "unidade_embalagem_estoque",
    "unidade_medida_embalagem_estoque",
]


def upgrade() -> None:
    """Upgrade schema."""
    for tabela in TABELAS:
        op.create_table(
            tabela,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("fazenda_id", sa.Integer(), nullable=True),
            sa.Column("nome", sa.String(), nullable=False),
            sa.Column("ativo", sa.Boolean(), nullable=False),
            sa.Column("criado_em", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["fazenda_id"], ["fazenda.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("nome", "fazenda_id", name=f"uq_{tabela}_nome_fazenda"),
        )
        op.create_index(op.f(f"ix_{tabela}_fazenda_id"), tabela, ["fazenda_id"], unique=False)
        op.create_index(op.f(f"ix_{tabela}_nome"), tabela, ["nome"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for tabela in reversed(TABELAS):
        op.drop_index(op.f(f"ix_{tabela}_nome"), table_name=tabela)
        op.drop_index(op.f(f"ix_{tabela}_fazenda_id"), table_name=tabela)
        op.drop_table(tabela)
