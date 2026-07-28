"""lote: excluir_da_sugestao

Lote (Configurações > Cadastro > Lotes) ganha uma flag pra marcar que ele
nunca deve ser sugerido automaticamente pelas rotinas de sugestão de
movimentação (GET /movimentacoes/sugestoes, POST /producao/sugestao-lote-evento),
mesmo que os critérios cadastrados nele bateriam com algum animal — útil
para lotes como enfermaria/quarentena/venda, onde a movimentação deve
continuar sempre manual (ver fazenda.rules.lote_criterios.lote_tem_criterio).

Revision ID: b7c8d9e0f1a2
Revises: 81ad18d4e7a9
Create Date: 2026-07-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = '81ad18d4e7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('lote', sa.Column('excluir_da_sugestao', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('lote', 'excluir_da_sugestao')
