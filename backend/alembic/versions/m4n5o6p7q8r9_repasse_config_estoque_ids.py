"""repasse_config.estoque_ids_json — vários produtos vinculados ao adesivo de detecção de cio

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-10-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "m4n5o6p7q8r9"
down_revision = "l3m4n5o6p7q8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("repasse_config"):
        return  # a tabela inteira ainda vai ser criada com o schema completo
    colunas = {c["name"] for c in insp.get_columns("repasse_config")}
    if "estoque_ids_json" not in colunas:
        op.add_column("repasse_config", sa.Column("estoque_ids_json", sa.String(), nullable=True))
        # Quem já tinha UM produto vinculado passa a ter a lista com ele — nada muda de comportamento.
        op.execute(sa.text(
            "UPDATE repasse_config SET estoque_ids_json = '[' || CAST(estoque_id AS VARCHAR) || ']' WHERE estoque_id IS NOT NULL"
        ))


def downgrade() -> None:
    op.drop_column("repasse_config", "estoque_ids_json")
