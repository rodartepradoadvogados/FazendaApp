"""contrato_fazenda: ciclo_pagamento (desconto por periodicidade)

Contrato CowData: reajuste dos planos de catálogo (+R$100 cada) e novos
descontos por pagamento adiantado (5% trimestral, 10% semestral, 20% anual —
ver PLANOS_CATALOGO/DESCONTO_CICLO_PAGAMENTO em fazenda/models/planos.py) não
mexem em schema — só esta coluna nova precisa de migração: registra qual
ciclo a fazenda escolheu, coluna aditiva com default "mensal" (sem desconto),
sem retroatividade nos contratos já fechados.

Revision ID: e7d38a401a68
Revises: efc2b9a74f51
Create Date: 2026-07-26 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7d38a401a68'
down_revision: Union[str, Sequence[str], None] = 'efc2b9a74f51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'contrato_fazenda',
        sa.Column('ciclo_pagamento', sa.String(), nullable=False, server_default='mensal'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('contrato_fazenda', 'ciclo_pagamento')
