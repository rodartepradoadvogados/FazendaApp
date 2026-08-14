"""servico: origem_diagnostico (fechamento automático por reinseminação)

Quando uma matriz é inseminada de novo, o serviço anterior que ainda estava
sem diagnóstico não pegou — por definição. O sistema passa a fechá-lo como
NEGATIVO automaticamente (ver fazenda/rules/perda_prenhez.py).

Esta coluna marca quais NEGATIVOs vieram dessa inferência e quais foram
lançados por gente. Sem ela não dá para desfazer o automático sem risco de
apagar um diagnóstico digitado por alguém, nem para o histórico mostrar a
diferença entre "o veterinário tocou e deu negativo" e "o sistema concluiu
que não pegou".

Coluna aditiva e nula: nenhum registro existente muda de comportamento.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-13 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('servico', sa.Column('origem_diagnostico', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('servico', 'origem_diagnostico')
