"""estoque: fazenda_id em Estoque, Fornecedor, MovimentoEstoque, EstoqueSemen, CompraSemen

Fecha o gap do domínio Estoque no retrofit multi-tenant. Mesma coluna
aditiva (nullable, com índice) já usada em Sanidade/Reprodutivo/Financeiro/
Pessoal/Animais/Lote, backfillada para a fazenda #1 (grandfathered) quando
ela já existir — sem retroatividade em nenhuma outra fazenda.

Nenhuma das 5 tabelas tem constraint de nome único a ajustar — `nome`/
`nome_item`/`touro_nome` são só indexados, não únicos (o cadastro de item de
estoque já convive com nomes repetidos hoje, ver rules/categorias.py) — é só
coluna aditiva.

Revision ID: 69f803f7f860
Revises: a2c22f9eaaac
Create Date: 2026-07-26 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69f803f7f860'
down_revision: Union[str, Sequence[str], None] = 'a2c22f9eaaac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABELAS = [
    'estoque',
    'fornecedor',
    'movimento_estoque',
    'estoque_semen',
    'compra_semen',
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    for tabela in _TABELAS:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    for tabela in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
