"""contrato_assinatura_zapsign: histórico de assinatura eletrônica do contrato

Tabela nova (ver fazenda/models/planos.py::ContratoAssinaturaZapSign) para o
botão "Assinar contrato" (fazenda/rules/zapsign.py) — não toca nenhuma
tabela existente.

Revision ID: 5029af5b3b49
Revises: e7d38a401a68
Create Date: 2026-07-26 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5029af5b3b49'
down_revision: Union[str, Sequence[str], None] = 'e7d38a401a68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'contrato_assinatura_zapsign',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('document_token', sa.String(), nullable=False),
        sa.Column('signer_token', sa.String(), nullable=True),
        sa.Column('sign_url', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('solicitado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('assinado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['solicitado_por_usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contrato_assinatura_zapsign_fazenda_id'), 'contrato_assinatura_zapsign', ['fazenda_id'], unique=False)
    op.create_index(op.f('ix_contrato_assinatura_zapsign_document_token'), 'contrato_assinatura_zapsign', ['document_token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_contrato_assinatura_zapsign_document_token'), table_name='contrato_assinatura_zapsign')
    op.drop_index(op.f('ix_contrato_assinatura_zapsign_fazenda_id'), table_name='contrato_assinatura_zapsign')
    op.drop_table('contrato_assinatura_zapsign')
