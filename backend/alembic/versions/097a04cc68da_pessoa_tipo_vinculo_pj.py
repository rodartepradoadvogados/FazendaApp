"""pessoa: tipo_vinculo (funcionario/pj), subtipo_pj, pagamento_mensal

Suporta o cadastro de Equipe CowData (ver fazenda/api/routers/painel_cowdata.py):
tipo de vínculo funcionário/PJ, subtipo da PJ (MEI/ME/EPP/Outros) e
pagamento mensal (equivalente a salario_base, mas para quem é PJ).

Revision ID: 097a04cc68da
Revises: e5e27b3f22aa
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '097a04cc68da'
down_revision: Union[str, Sequence[str], None] = 'e5e27b3f22aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('pessoa', sa.Column('tipo_vinculo', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('subtipo_pj', sa.String(), nullable=True))
    op.add_column('pessoa', sa.Column('pagamento_mensal', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pessoa', 'pagamento_mensal')
    op.drop_column('pessoa', 'subtipo_pj')
    op.drop_column('pessoa', 'tipo_vinculo')
