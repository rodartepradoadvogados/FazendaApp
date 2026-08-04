"""lancamento_anexo_supabase

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-04 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, Sequence[str], None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("lancamento_anexo", sa.Column("categoria", sa.String(), nullable=True))
    op.add_column("lancamento_anexo", sa.Column("caminho_storage", sa.String(), nullable=True))
    # batch mode: SQLite (dev/testes) não suporta ALTER COLUMN direto — precisa
    # recriar a tabela por baixo dos panos; Postgres (produção) ignora o batch
    # e faz o ALTER COLUMN normal.
    with op.batch_alter_table("lancamento_anexo") as batch_op:
        batch_op.alter_column("conteudo", existing_type=sa.LargeBinary(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("lancamento_anexo") as batch_op:
        batch_op.alter_column("conteudo", existing_type=sa.LargeBinary(), nullable=False)
    op.drop_column("lancamento_anexo", "caminho_storage")
    op.drop_column("lancamento_anexo", "categoria")
