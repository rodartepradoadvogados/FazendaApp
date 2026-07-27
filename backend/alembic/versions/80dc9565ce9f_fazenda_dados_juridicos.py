"""fazenda: documento/endereco/representante (dados jurídicos)

Colunas aditivas na tabela fazenda — usadas pelo contrato-modelo e pela
cobrança (Asaas/ZapSign) como padrão persistido, em vez de exigir digitar de
novo a cada contrato/cobrança (ver fazenda/rules/contrato_render.py e
fazenda/api/routers/fazendas.py::editar_fazenda).

Revision ID: 80dc9565ce9f
Revises: 557612f98f71
Create Date: 2026-07-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80dc9565ce9f'
down_revision: Union[str, Sequence[str], None] = '557612f98f71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fazenda', sa.Column('documento', sa.String(), nullable=True))
    op.add_column('fazenda', sa.Column('endereco', sa.String(), nullable=True))
    op.add_column('fazenda', sa.Column('representante_nome', sa.String(), nullable=True))
    op.add_column('fazenda', sa.Column('representante_cpf', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('fazenda', 'representante_cpf')
    op.drop_column('fazenda', 'representante_nome')
    op.drop_column('fazenda', 'endereco')
    op.drop_column('fazenda', 'documento')
