"""Diária: data_fim + ajuste manual de número de diárias

Controle de diárias ganha data de fim prevista (avisa no último dia via
Agenda, ver eventos_diaria_fim em routers/agenda.py) e um botão de editar
que corrige o contador (`ajuste_numero_diarias` + `ajuste_numero_diarias_em`
como novo checkpoint, ver _resumo_diaria em routers/cadastro/rh_contratos.py).

Revision ID: d4c7a4de4f1e
Revises: d7e8f9a0b1c2
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4c7a4de4f1e'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('diaria', sa.Column('data_fim', sa.Date(), nullable=True))
    op.add_column('diaria', sa.Column('ajuste_numero_diarias', sa.Integer(), nullable=True))
    op.add_column('diaria', sa.Column('ajuste_numero_diarias_em', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('diaria', 'ajuste_numero_diarias_em')
    op.drop_column('diaria', 'ajuste_numero_diarias')
    op.drop_column('diaria', 'data_fim')
