"""lote: adiciona mudanca_automatica e lote_destino_codigo (PUSH)

Sessão — mudança automática de lote (modelo PUSH):
- `mudanca_automatica` (bool): quando True, ESTE lote é a ORIGEM/gatilho;
  um animal ATUALMENTE neste lote que atende TODOS os critérios
  cumulativos deve ser PROPOSTO para mover ao lote_destino_codigo.
  Inverte a semântica original PULL (o lote com critério era o destino).
- `lote_destino_codigo` (string): código de 2 dígitos do lote destino
  (mesmo padrão do campo `codigo` do Lote). Se vazio, não gera proposta.
- Mutuamente exclusivo com `excluir_da_sugestao` (validado no router).
- Patrimonio: campos de soft-delete (excluido, data_exclusao, motivo_exclusao)
  para exclusão definitiva que "some" da listagem mas preserva histórico.

Revision ID: a7b8c9d0e1f2
Revises: fd30a36c88cf
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'fd30a36c88cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Lote: mudanca_automatica + lote_destino_codigo
    op.add_column('lote', sa.Column('mudanca_automatica', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('lote', sa.Column('lote_destino_codigo', sa.String(), nullable=True))

    # Patrimonio: soft-delete fields
    op.add_column('patrimonio', sa.Column('excluido', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('patrimonio', sa.Column('data_exclusao', sa.Date(), nullable=True))
    op.add_column('patrimonio', sa.Column('motivo_exclusao', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('patrimonio', 'motivo_exclusao')
    op.drop_column('patrimonio', 'data_exclusao')
    op.drop_column('patrimonio', 'excluido')
    op.drop_column('lote', 'lote_destino_codigo')
    op.drop_column('lote', 'mudanca_automatica')