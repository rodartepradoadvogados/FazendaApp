"""parametro_sugestao_movimentacao: fazenda_id (de-singletoniza)

Peça do Fase 4C (Rebanho/Lote) que não foi coberta pelo retrofit paralelo
"Fase 0" (a2c22f9eaaac) — aquela migração deixou `ParametroSugestaoMovimentacao`
de fora de propósito, mas o modelo já foi de-singletonizado (mesmo padrão de
`ParametroDiariaPadrao` na Fase 4B): passa de linha única fixa (id=1) para
uma linha por fazenda, com `UniqueConstraint("fazenda_id")`.

Revision ID: a9b0c1d2e3f4
Revises: 69f803f7f860
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, Sequence[str], None] = '69f803f7f860'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABELA = 'parametro_sugestao_movimentacao'
_CONSTRAINT = 'uq_parametro_sugestao_movimentacao_fazenda'


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table(_TABELA):
        return
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    op.add_column(_TABELA, sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f(f'ix_{_TABELA}_fazenda_id'), _TABELA, ['fazenda_id'], unique=False)
    if fazenda_1_existe:
        conn.execute(sa.text(f"UPDATE {_TABELA} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
    with op.batch_alter_table(_TABELA, schema=None) as batch_op:
        batch_op.create_unique_constraint(_CONSTRAINT, ['fazenda_id'])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table(_TABELA):
        return
    with op.batch_alter_table(_TABELA, schema=None) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_='unique')
    op.drop_index(op.f(f'ix_{_TABELA}_fazenda_id'), table_name=_TABELA)
    op.drop_column(_TABELA, 'fazenda_id')
