"""secagem: vacina_pre_parto (resposta explícita, para histórico)

Registra a resposta explícita de "aplicar vacina pré-parto?" dada no momento
da secagem — antes só existia a pendência na Agenda quando a resposta era
"sim"; quando "não", nada ficava gravado. Coluna aditiva e nula: nenhuma
secagem existente muda de comportamento.

Revision ID: c159d14e36ad
Revises: 6cfa00787699
Create Date: 2026-08-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c159d14e36ad'
down_revision: Union[str, Sequence[str], None] = '6cfa00787699'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('secagem', sa.Column('vacina_pre_parto', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('secagem', 'vacina_pre_parto')
