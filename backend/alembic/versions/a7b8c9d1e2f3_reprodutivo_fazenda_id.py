"""reprodutivo: fazenda_id em servico/parto/colostragem/protocolo IATF/tipo-metodo servico

Revision ID: a7b8c9d1e2f3
Revises: f6a7b8c9d1e2
Create Date: 2026-07-23 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Cada tabela do domínio reprodutivo ganha a mesma coluna aditiva
# (nullable, com índice) já usada em Animal/ContaCorrente/CentroCusto/Pessoa —
# sem retroatividade em nenhum outro cadastro. Backfill só roda se a fazenda
# #1 (grandfathered) já existir.
_TABELAS = [
    'servico',
    'tipo_servico_reprodutivo',
    'metodo_servico_reprodutivo',
    'protocolo_iatf_lancamento',
    'protocolo_iatf_aplicacao',
    'protocolo_iatf_hormonio',
    'parto',
    'colostragem_bezerra',
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    for tabela in _TABELAS:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    for tabela in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
