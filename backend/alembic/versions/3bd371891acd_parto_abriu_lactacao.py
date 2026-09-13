"""parto.abriu_lactacao

Correção do bug de `Parto.ordem_parto` — ver `fazenda/rules/parto.py` e
`fazenda/api/routers/reproducao.py::encerrar_gestacao`. Um aborto que abre
lactação (`EncerramentoGestacaoIn.abrir_lactacao=True` com `tipo="aborto"`)
passa a ser produtivo: conta na ordem de parto da matriz, tanto quanto um
parto normal conta.

`Parto.abriu_lactacao` é o registro, no próprio `Parto`, de que ESTE aborto
específico abriu lactação — a informação vive de fato em `Lactacao.origem`
(`ORIGEM_ABORTO`), mas `rules.parto.eh_parto_produtivo` precisa saber decidir
produtividade sem Session (função pura, testável sem banco — ver docstring do
módulo), então o flag é gravado uma vez, no momento da criação do `Parto`.

Nasce `False`: todo `Parto` já existente (parto normal, natimorto, aborto sem
lactação, e também o aborto QUE já abriu lactação antes desta correção)
recebe `False` — não há como saber retroativamente, a partir só do `Parto`,
se aquele aborto específico abriu lactação (a `Lactacao` correspondente
existe, mas casar as duas tabelas de forma seletiva é reescrita de dado
histórico, não migração automática; a ferramenta administrativa de
reconstrução de `Parto.ordem_parto`, Configurações > Cadastro > Ordem de
Parto, é o lugar para revisar esses casos manualmente se precisar).

Revision ID: 3bd371891acd
Revises: dae0e0884347
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3bd371891acd'
down_revision: Union[str, Sequence[str], None] = 'dae0e0884347'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Idempotente por coluna (`has_column`), como as demais migrações aditivas
    deste repositório — um banco de dev/teste pode já ter a coluna via
    `create_all` antes do Alembic chegar.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas_parto = {c['name'] for c in insp.get_columns('parto')} if insp.has_table('parto') else set()
    if 'abriu_lactacao' not in colunas_parto:
        with op.batch_alter_table('parto', schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'abriu_lactacao', sa.Boolean(), nullable=False, server_default=sa.false(),
            ))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas_parto = {c['name'] for c in insp.get_columns('parto')} if insp.has_table('parto') else set()
    if 'abriu_lactacao' in colunas_parto:
        with op.batch_alter_table('parto', schema=None) as batch_op:
            batch_op.drop_column('abriu_lactacao')
