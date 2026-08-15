"""entrega_leite_mensal: unidade (kg | L)

A entrega ao laticínio pode ser contratada em quilo ou em litro, e o controle
leiteiro é sempre em quilo. Até aqui o volume entregue era subtraído do
controle sem conversão — quem lançava em litro via o "não entregue" (leite dos
bezerros + equipe) inflado em ~2,9%, que é a densidade do leite (1 L ≈ 1,029
kg, ver DENSIDADE_LEITE_KG_POR_L em fazenda/rules/unidades.py).

Coluna aditiva com default "kg": todo lançamento existente continua sendo lido
exatamente como era (o sistema já os tratava como quilo na comparação), então
nenhum número histórico muda com esta migração.

Revision ID: c4d5e6f7a8b9
Revises: a8b9c0d1e2f3
Create Date: 2026-08-13 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'entrega_leite_mensal',
        sa.Column('unidade', sa.String(), nullable=False, server_default='kg'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('entrega_leite_mensal', 'unidade')
