"""cobranca_boleto/cobranca_pix: cobrança da assinatura CowData (BB)

Tabelas novas (ver fazenda/models/cobranca.py e fazenda/rules/banco_brasil.py)
para o scaffold de boleto/PIX via Banco do Brasil — não toca nenhuma tabela
existente. Distintas do módulo Financeiro de cada fazenda.

Revision ID: a91e6f849002
Revises: 5029af5b3b49
Create Date: 2026-07-26 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a91e6f849002'
down_revision: Union[str, Sequence[str], None] = '5029af5b3b49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'cobranca_boleto',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('numero_convenio', sa.String(), nullable=False),
        sa.Column('nosso_numero', sa.String(), nullable=True),
        sa.Column('linha_digitavel', sa.String(), nullable=True),
        sa.Column('codigo_barras', sa.String(), nullable=True),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('data_vencimento', sa.Date(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('pago_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cobranca_boleto_fazenda_id'), 'cobranca_boleto', ['fazenda_id'], unique=False)

    op.create_table(
        'cobranca_pix',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('txid', sa.String(), nullable=False),
        sa.Column('pix_copia_cola', sa.String(), nullable=True),
        sa.Column('qrcode_base64', sa.String(), nullable=True),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('pago_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cobranca_pix_fazenda_id'), 'cobranca_pix', ['fazenda_id'], unique=False)
    op.create_index(op.f('ix_cobranca_pix_txid'), 'cobranca_pix', ['txid'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_cobranca_pix_txid'), table_name='cobranca_pix')
    op.drop_index(op.f('ix_cobranca_pix_fazenda_id'), table_name='cobranca_pix')
    op.drop_table('cobranca_pix')
    op.drop_index(op.f('ix_cobranca_boleto_fazenda_id'), table_name='cobranca_boleto')
    op.drop_table('cobranca_boleto')
