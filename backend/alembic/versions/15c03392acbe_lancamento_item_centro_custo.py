"""lancamento_item: centro_custo (override por item dentro da mesma nota)

Uma nota fiscal com vários itens pode precisar distribuir cada item para um
centro de custo diferente, mesmo pagando tudo com o mesmo comprovante — este
campo, quando preenchido, sobrepõe o centro de custo da nota (ContaGerencial.
centro_custo) só para aquele item; None (a maioria) continua usando o da
nota inteira. Mesmo padrão do já existente codigo_conta_gerencial por item.

Coluna aditiva e nula: nenhum item existente muda de comportamento.

Revision ID: 15c03392acbe
Revises: c159d14e36ad
Create Date: 2026-08-16 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15c03392acbe'
down_revision: Union[str, Sequence[str], None] = 'c159d14e36ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lancamento_item', sa.Column('centro_custo', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('lancamento_item', 'centro_custo')
