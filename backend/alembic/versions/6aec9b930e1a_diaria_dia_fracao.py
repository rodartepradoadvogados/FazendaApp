"""diaria_dia: fração do dia (meia diária)

Acrescenta `diaria_dia.fracao` (float, opcional) — permite marcar um dia como
meia diária (fracao=0.5) além de folga (fracao=0.0/None, comportamento de
sempre) no calendário esparso de dias trabalhados de uma Diária. Ver
`_fracao_dia`/`salvar_dias_diaria` em routers/cadastro/rh_contratos.py.

Revision ID: 6aec9b930e1a
Revises: c8e91a4f6b23
Create Date: 2026-08-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6aec9b930e1a'
down_revision: Union[str, Sequence[str], None] = 'c8e91a4f6b23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    colunas = {c['name'] for c in insp.get_columns('diaria_dia')}
    if 'fracao' not in colunas:
        op.add_column('diaria_dia', sa.Column('fracao', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('diaria_dia', 'fracao')
