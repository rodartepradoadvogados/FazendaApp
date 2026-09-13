"""animal: descarte_previsto_em (data prevista da saída do rebanho)

Complemento de `a_descartar_em` (migração c576e514aa3e). São duas datas com
papéis diferentes, e confundi-las é o risco desta mudança:

  a_descartar_em       QUANDO SE DECIDIU descartar. É a data que o motor do
                       programa reprodutivo lê (`descartada_em`) para saber a
                       partir de quando o animal sai do denominador.
  descarte_previsto_em QUANDO SE PRETENDE FAZER — o plano físico da saída (a
                       boiada, o caminhão, a próxima venda). Pode ser meses
                       depois da decisão.

A coluna nova é INFORMATIVA: não entra em cálculo reprodutivo nenhum. A saída
do programa continua sendo na data da DECISÃO, porque quem decide descartar
para de inseminar naquele momento — a saída reprodutiva é a decisão, não o
caminhão. Há teste sentinela travando isso (preencher a previsão não pode
mover taxa nenhuma do painel).

OPCIONAL DE PROPÓSITO: nem toda decisão de descarte nasce com data marcada, e
NULL aqui significa "sem previsão definida" — um estado legítimo, não uma
pendência. As telas não devem tratar o vazio como erro a corrigir.

Sem backfill, pelo mesmo motivo da migração anterior: não há de onde tirar a
previsão de quem já estava marcado, e inventá-la produziria um plano que
ninguém fez.

Coluna aditiva e nula: nenhum registro existente muda de comportamento.

Revision ID: d8f1a2c47b93
Revises: c576e514aa3e
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f1a2c47b93'
down_revision: Union[str, Sequence[str], None] = 'c576e514aa3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('animal', sa.Column('descarte_previsto_em', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('animal', 'descarte_previsto_em')
