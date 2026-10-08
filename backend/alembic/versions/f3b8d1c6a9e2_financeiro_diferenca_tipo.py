"""financeiro Fase A (PR 7): conta_gerencial.diferenca_tipo (abatimento x financeiro)

Coluna nova, nula, em `conta_gerencial`: o que a diferença apurada na baixa
(`desconto_acrescimo`) é para os relatórios — NULL = "financeiro" (padrão,
vai para Outras receitas e despesas) ou "abatimento" (o desconto reduz o valor
da própria conta). Ver fazenda/rules/juros_descontos.py.

ADITIVA, idempotente (coluna já criada pelo `create_all` do boot não aborta o
upgrade) e SEM backfill: nenhuma linha existente é tocada (NULL = o padrão).
O downgrade só remove a coluna.

Revision ID: f3b8d1c6a9e2
Revises: e5a9c3f1b742
Create Date: 2026-10-08 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3b8d1c6a9e2'
down_revision: Union[str, Sequence[str], None] = 'e5a9c3f1b742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = 'conta_gerencial'
COLUNA = 'diferenca_tipo'


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABELA):
        return
    if COLUNA in {c['name'] for c in insp.get_columns(TABELA)}:
        return
    with op.batch_alter_table(TABELA) as batch:
        batch.add_column(sa.Column(COLUNA, sa.String(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABELA):
        return
    if COLUNA not in {c['name'] for c in insp.get_columns(TABELA)}:
        return
    with op.batch_alter_table(TABELA) as batch:
        batch.drop_column(COLUNA)
