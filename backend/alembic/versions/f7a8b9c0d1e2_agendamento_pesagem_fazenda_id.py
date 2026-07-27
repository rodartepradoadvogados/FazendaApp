"""agendamento_pesagem: fazenda_id (Fase 4D)

Fecha um gap esquecido no retrofit multi-tenant da Sanidade (c9d1e2f3a4b5):
`agendamento_pesagem` (Cadastro > Sanitário > Agendamento de pesagem) nunca
ganhou a coluna, então o cadastro de periodicidade de pesagem vazava entre
fazendas (GET sem filtro, POST sem carimbo, PUT/DELETE sem checagem de
posse) — mesma coluna aditiva (nullable, com índice) já usada em
Reprodutivo/CentroCusto/Pessoa/Sanidade, backfillada para a fazenda #1
(grandfathered) quando ela já existir.

Revision ID: f7a8b9c0d1e2
Revises: a9b0c1d2e3f4
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'a9b0c1d2e3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELA = 'agendamento_pesagem'


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    op.add_column(_TABELA, sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f(f'ix_{_TABELA}_fazenda_id'), _TABELA, ['fazenda_id'], unique=False)
    if fazenda_1_existe:
        conn.execute(sa.text(f"UPDATE {_TABELA} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f(f'ix_{_TABELA}_fazenda_id'), table_name=_TABELA)
    op.drop_column(_TABELA, 'fazenda_id')
