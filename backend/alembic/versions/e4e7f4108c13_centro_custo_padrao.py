"""centro_custo: padrao

Centro de custo (Configurações > Parâmetros financeiros > Centro de custo)
ganha a flag `padrao` — no máximo 1 marcado por fazenda, usado
automaticamente pelo novo Lançamento simplificado (Lançamentos > Financeiro >
Contas a pagar/receber) no lugar de pedir centro de custo naquela tela. A
regra de "só 1 por fazenda" é aplicada pela API (POST/PUT /financeiro/
centros-custo — ver `_desmarcar_outros_centro_custo_padrao` em
fazenda/api/routers/financeiro.py), não por uma constraint de banco: um
índice único parcial (WHERE padrao) não é portável entre SQLite e Postgres
sem duas migrações diferentes, e a API já garante a invariante numa única
transação a cada escrita.

Revision ID: e4e7f4108c13
Revises: 17e59e018562
Create Date: 2026-08-23 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4e7f4108c13'
down_revision: Union[str, Sequence[str], None] = '17e59e018562'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('centro_custo', sa.Column('padrao', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('centro_custo', 'padrao')
