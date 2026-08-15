"""cartao_credito

Revision ID: a29c96161bed
Revises: c6d7e8f9a0b1
Create Date: 2026-08-04 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a29c96161bed'
down_revision: Union[str, Sequence[str], None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cartao_credito",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fazenda_id", sa.Integer(), nullable=True),
        sa.Column("apelido", sa.String(), nullable=False),
        sa.Column("bandeira", sa.String(), nullable=True),
        sa.Column("banco_emissor", sa.String(), nullable=True),
        sa.Column("conta_bancaria_id", sa.Integer(), nullable=True),
        sa.Column("dia_fechamento", sa.Integer(), nullable=False),
        sa.Column("dia_vencimento", sa.Integer(), nullable=False),
        sa.Column("limite", sa.Float(), nullable=True),
        sa.Column("controla_milhas", sa.Boolean(), nullable=False),
        sa.Column("milhas_por_real", sa.Float(), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conta_bancaria_id"], ["conta_corrente.id"]),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazenda.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cartao_credito_fazenda_id"), "cartao_credito", ["fazenda_id"], unique=False)

    op.create_table(
        "fatura_cartao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fazenda_id", sa.Integer(), nullable=True),
        sa.Column("cartao_id", sa.Integer(), nullable=False),
        sa.Column("competencia", sa.String(), nullable=False),
        sa.Column("data_fechamento", sa.Date(), nullable=False),
        sa.Column("data_vencimento", sa.Date(), nullable=False),
        sa.Column("valor_total", sa.Float(), nullable=True),
        sa.Column("milhas_acumuladas", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("numero_lancamento", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cartao_id"], ["cartao_credito.id"]),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazenda.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cartao_id", "competencia", name="uq_fatura_cartao_competencia"),
    )
    op.create_index(op.f("ix_fatura_cartao_fazenda_id"), "fatura_cartao", ["fazenda_id"], unique=False)
    op.create_index(op.f("ix_fatura_cartao_cartao_id"), "fatura_cartao", ["cartao_id"], unique=False)
    op.create_index(op.f("ix_fatura_cartao_competencia"), "fatura_cartao", ["competencia"], unique=False)

    op.create_table(
        "lancamento_cartao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fazenda_id", sa.Integer(), nullable=True),
        sa.Column("cartao_id", sa.Integer(), nullable=False),
        sa.Column("fatura_id", sa.Integer(), nullable=False),
        sa.Column("data_compra", sa.Date(), nullable=False),
        sa.Column("descricao", sa.String(), nullable=False),
        sa.Column("codigo_conta_gerencial", sa.String(), nullable=True),
        sa.Column("nome_conta_gerencial", sa.String(), nullable=True),
        sa.Column("centro_custo", sa.String(), nullable=True),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("parcela_num", sa.Integer(), nullable=True),
        sa.Column("parcela_total", sa.Integer(), nullable=True),
        sa.Column("observacao", sa.String(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cartao_id"], ["cartao_credito.id"]),
        sa.ForeignKeyConstraint(["fatura_id"], ["fatura_cartao.id"]),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazenda.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lancamento_cartao_fazenda_id"), "lancamento_cartao", ["fazenda_id"], unique=False)
    op.create_index(op.f("ix_lancamento_cartao_cartao_id"), "lancamento_cartao", ["cartao_id"], unique=False)
    op.create_index(op.f("ix_lancamento_cartao_fatura_id"), "lancamento_cartao", ["fatura_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_lancamento_cartao_fatura_id"), table_name="lancamento_cartao")
    op.drop_index(op.f("ix_lancamento_cartao_cartao_id"), table_name="lancamento_cartao")
    op.drop_index(op.f("ix_lancamento_cartao_fazenda_id"), table_name="lancamento_cartao")
    op.drop_table("lancamento_cartao")

    op.drop_index(op.f("ix_fatura_cartao_competencia"), table_name="fatura_cartao")
    op.drop_index(op.f("ix_fatura_cartao_cartao_id"), table_name="fatura_cartao")
    op.drop_index(op.f("ix_fatura_cartao_fazenda_id"), table_name="fatura_cartao")
    op.drop_table("fatura_cartao")

    op.drop_index(op.f("ix_cartao_credito_fazenda_id"), table_name="cartao_credito")
    op.drop_table("cartao_credito")
