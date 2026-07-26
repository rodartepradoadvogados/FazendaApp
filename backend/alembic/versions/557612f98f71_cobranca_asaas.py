"""cobranca_asaas: cobrança/assinatura da CowData via Asaas

Tabela nova (ver fazenda/models/cobranca.py::CobrancaAsaas e
fazenda/rules/asaas.py) — não toca nenhuma tabela existente. Substitui/
complementa o scaffold do Banco do Brasil (cobranca_boleto/cobranca_pix,
migração a91e6f849002) como integração ativa de cobrança da assinatura.

Revision ID: 557612f98f71
Revises: a91e6f849002
Create Date: 2026-07-26 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '557612f98f71'
down_revision: Union[str, Sequence[str], None] = 'a91e6f849002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'cobranca_asaas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('referencia_asaas', sa.String(), nullable=False),
        sa.Column('asaas_customer_id', sa.String(), nullable=False),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('pago_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cobranca_asaas_fazenda_id'), 'cobranca_asaas', ['fazenda_id'], unique=False)
    op.create_index(op.f('ix_cobranca_asaas_referencia_asaas'), 'cobranca_asaas', ['referencia_asaas'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_cobranca_asaas_referencia_asaas'), table_name='cobranca_asaas')
    op.drop_index(op.f('ix_cobranca_asaas_fazenda_id'), table_name='cobranca_asaas')
    op.drop_table('cobranca_asaas')
