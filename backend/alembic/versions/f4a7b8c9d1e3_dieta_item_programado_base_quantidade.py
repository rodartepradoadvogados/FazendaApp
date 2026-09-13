"""dieta_item_programado: base_quantidade (override por item)

Até aqui `DietaLancamento.base_quantidade` ("total" do lote/dia ou "animal"
por cabeça/dia) valia para TODOS os itens do lançamento — um único dropdown
por dieta. O pedido do proprietário foi poder misturar as duas bases no
MESMO lançamento (ex.: silagem em total do lote, concentrado por cabeça).

Esta coluna é o override por item: `None` (padrão, todo item existente até
aqui) significa "herda a base da dieta" — exatamente o comportamento atual,
sem mudança nenhuma para lançamentos já feitos (manuais, do app móvel ou de
Formulação de Dietas, nenhum dos quais preenche este campo). Só quando o
item vem com "total" ou "animal" explícito ele passa a ser calculado com a
SUA PRÓPRIA base, independente do que a dieta diz — ver `_base_efetiva` em
fazenda/api/routers/alimentacao.py.

Coluna aditiva e nula: nenhum registro existente muda de comportamento.

Revision ID: f4a7b8c9d1e3
Revises: e3bc1c978262
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a7b8c9d1e3'
down_revision: Union[str, Sequence[str], None] = 'e3bc1c978262'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('dieta_item_programado', sa.Column('base_quantidade', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dieta_item_programado', 'base_quantidade')
