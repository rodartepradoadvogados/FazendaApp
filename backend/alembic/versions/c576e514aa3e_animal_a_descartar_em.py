"""animal: a_descartar_em (data da marcação de descarte)

`Animal.a_descartar` é um booleano sem data — para reconstrução histórica
(fazenda/rules/programa_reprodutivo.py, que recalcula o estado do rebanho em
datas passadas) isso faz um animal marcado HOJE desaparecer de TODOS os
ciclos passados, inclusive dos em que estava ativo e devia contar no
denominador. Esta coluna registra quando a marcação passou a valer.

SEM BACKFILL DE PROPÓSITO: os animais já marcados como `a_descartar=True`
antes desta migração ficam com `a_descartar_em = NULL`, e não com a data de
hoje, a da criação do registro, ou qualquer outra estimativa. Inventar uma
data produziria um histórico plausível e falso — pior que um histórico
ausente, porque ninguém consegue distinguir um retroativo real de um
chutado. Com NULL, quem lê sabe que não sabe.

Quem for consumir a coluna trata NULL como "marcação sem data" e adota o
mesmo critério que `baixada_em()` (mesmo módulo) já usa para `ativo=False`
sem `data_baixa`: marcação sem data é tratada como já vigente, porque é o
que o dado permite afirmar — não há como assumir que a marcação é recente
nem que é antiga.

Coluna aditiva e nula: nenhum registro existente muda de comportamento.

Revision ID: c576e514aa3e
Revises: eb68f8993eb9
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c576e514aa3e'
down_revision: Union[str, Sequence[str], None] = 'eb68f8993eb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('animal', sa.Column('a_descartar_em', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('animal', 'a_descartar_em')
