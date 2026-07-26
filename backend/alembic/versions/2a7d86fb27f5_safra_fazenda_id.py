"""agricultura: fazenda_id em Safra

Fecha o gap do domínio Agricultura no retrofit multi-tenant: mesma coluna
aditiva (nullable, com índice) já usada em Sanidade/Reprodutivo/Financeiro,
backfillada para a fazenda #1 (grandfathered) quando ela já existir — sem
retroatividade em nenhuma outra fazenda. `nome` (único globalmente) troca
para unique(nome, fazenda_id) — senão a 2ª fazenda nunca conseguiria
cadastrar uma safra com nome já usado pela 1ª.

Revision ID: 2a7d86fb27f5
Revises: 63765dda4ff8
Create Date: 2026-07-26 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '2a7d86fb27f5'
down_revision: Union[str, Sequence[str], None] = '63765dda4ff8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # `safra` nunca ganhou migração própria de criação (nasceu depois do
    # baseline, criada só pela rede de segurança `SQLModel.metadata.create_all`
    # em `fazenda/database.py::create_db_and_tables`, que roda DEPOIS do
    # Alembic) — banco totalmente vazio (ex.: suíte de testes, cada run com
    # um SQLite novo) ainda não tem a tabela neste ponto. Nesse caso, pula o
    # ALTER: create_all() cria `safra` já com `fazenda_id` (a coluna já está
    # no modelo SQLModel), sem precisar desta migração.
    if 'safra' not in inspect(conn).get_table_names():
        return

    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    op.add_column('safra', sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_safra_fazenda_id'), 'safra', ['fazenda_id'], unique=False)
    if fazenda_1_existe:
        conn.execute(sa.text("UPDATE safra SET fazenda_id = 1 WHERE fazenda_id IS NULL"))

    with op.batch_alter_table('safra', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_safra_nome')
        except Exception:
            pass
        batch_op.create_index('ix_safra_nome', ['nome'], unique=False)
        batch_op.create_unique_constraint('uq_safra_nome_fazenda', ['nome', 'fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    if 'safra' not in inspect(conn).get_table_names():
        return
    with op.batch_alter_table('safra', schema=None) as batch_op:
        batch_op.drop_constraint('uq_safra_nome_fazenda', type_='unique')
        batch_op.drop_index('ix_safra_nome')
        batch_op.create_index('ix_safra_nome', ['nome'], unique=True)
    op.drop_index(op.f('ix_safra_fazenda_id'), table_name='safra')
    op.drop_column('safra', 'fazenda_id')
