"""financeiro: fazenda_id em Patrimônio e Curva ABC (Fase 3D)

Fecha o gap de Patrimônio/Manutenção de Patrimônio e Curva ABC no retrofit
multi-tenant: mesma coluna aditiva (nullable, com índice) já usada em
ContaGerencial/PlanoContaGerencial/Pedido (Fases 3A/3B/3C — f4a5b6c7d8e9),
backfillada para a fazenda #1 (grandfathered) quando ela já existir — sem
retroatividade em nenhuma outra fazenda.

Nenhuma das três tabelas tem campo único global — só ganham a coluna
aditiva, sem mudança de constraint (diferente do padrão de Pedido/
PlanoContaGerencial).

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-24 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, Sequence[str], None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABELAS = [
    'patrimonio',
    'manutencao_patrimonio',
    'curva_abc',
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
