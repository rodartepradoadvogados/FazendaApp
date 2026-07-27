"""alimentacao_estado: converte de singleton (id=1) para uma linha por fazenda

Gap deixado de propósito pela efc2b9a74f51 (Alimentação fazenda_id): o
estado de baixa automática de estoque (`ultima_data_deducao`) ficava numa
única linha global (id=1), compartilhada por todas as fazendas — a segunda
fazenda cadastrada herdaria (ou corromperia) a data de baixa da primeira.
Mesmo padrão de conversão singleton -> por-fazenda já usado em
ParametroDiariaPadrao/MetaRecria: coluna aditiva (nullable, indexada) +
unique(fazenda_id), backfillada para a fazenda #1 (grandfathered).

Revision ID: a3f9c1e2d4b6
Revises: e9688fcec98f
Create Date: 2026-07-27 01:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c1e2d4b6'
down_revision: Union[str, Sequence[str], None] = 'e9688fcec98f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    op.add_column('alimentacao_estado', sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_alimentacao_estado_fazenda_id'), 'alimentacao_estado', ['fazenda_id'], unique=False)
    if fazenda_1_existe:
        conn.execute(sa.text("UPDATE alimentacao_estado SET fazenda_id = 1 WHERE id = 1 AND fazenda_id IS NULL"))
    with op.batch_alter_table('alimentacao_estado', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_alimentacao_estado_fazenda', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('alimentacao_estado', schema=None) as batch_op:
        batch_op.drop_constraint('uq_alimentacao_estado_fazenda', type_='unique')
    op.drop_index(op.f('ix_alimentacao_estado_fazenda_id'), table_name='alimentacao_estado')
    op.drop_column('alimentacao_estado', 'fazenda_id')
