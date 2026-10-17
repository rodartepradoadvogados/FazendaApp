"""agenda_reprodutiva_cards — cards configuráveis da Agenda Reprodutiva salvos por fazenda

Revision ID: l3m4n5o6p7q8
Revises: 7e3f1a9c5b24
Create Date: 2026-10-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "l3m4n5o6p7q8"
down_revision = "7e3f1a9c5b24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("agenda_reprodutiva_cards"):
        return  # a rede de segurança do startup (create_all) pode ter criado antes
    op.create_table(
        "agenda_reprodutiva_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fazenda_id", sa.Integer(), nullable=True),
        sa.Column("cards_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("atualizado_por_usuario_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazenda.id"]),
        sa.ForeignKeyConstraint(["atualizado_por_usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fazenda_id", name="uq_agenda_reprodutiva_cards_fazenda"),
    )
    op.create_index(op.f("ix_agenda_reprodutiva_cards_fazenda_id"), "agenda_reprodutiva_cards", ["fazenda_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agenda_reprodutiva_cards_fazenda_id"), table_name="agenda_reprodutiva_cards")
    op.drop_table("agenda_reprodutiva_cards")
