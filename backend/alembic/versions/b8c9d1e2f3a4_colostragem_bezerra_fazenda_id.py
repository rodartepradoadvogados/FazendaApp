"""colostragem_bezerra: unique(numero_animal) -> unique(numero_animal, fazenda_id)

A coluna fazenda_id da colostragem_bezerra em si já foi criada pela migração
anterior (a7b8c9d1e2f3_reprodutivo_fazenda_id.py — a tabela estava na lista
_TABELAS, só o campo no modelo SQLModel é que tinha ficado de fora). O que
faltava era só isto: sem trocar o unique(numero_animal) global por
unique(numero_animal, fazenda_id), a 2ª fazenda nunca conseguiria cadastrar
colostragem de uma cria com o mesmo número já usado por outra fazenda —
mesmo padrão já usado em centro_custo (ver
c3d4e5f6a7b9_centro_custo_pessoa_calendario_fazenda_id.py).

Revision ID: b8c9d1e2f3a4
Revises: a7b8c9d1e2f3
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8c9d1e2f3a4'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('colostragem_bezerra', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_colostragem_bezerra_numero_animal')
        except Exception:
            pass
        batch_op.create_index('ix_colostragem_bezerra_numero_animal', ['numero_animal'], unique=False)
        batch_op.create_unique_constraint('uq_colostragem_bezerra_numero_fazenda', ['numero_animal', 'fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('colostragem_bezerra', schema=None) as batch_op:
        batch_op.drop_constraint('uq_colostragem_bezerra_numero_fazenda', type_='unique')
        batch_op.drop_index('ix_colostragem_bezerra_numero_animal')
        batch_op.create_index('ix_colostragem_bezerra_numero_animal', ['numero_animal'], unique=True)
