"""fatura de fornecedor: cronograma do parcelamento e historico

Colunas `parcelas_primeiro`, `parcelas_intervalo`, `parcelamento_origem` em `fatura_fornecedor` e a
tabela `fatura_fornecedor_evento`. ADITIVA e idempotente.

Revision ID: b9d3f7a1c528
Revises: a8c2e6f0b417
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9d3f7a1c528'
down_revision: Union[str, Sequence[str], None] = 'a8c2e6f0b417'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c['name'] for c in insp.get_columns('fatura_fornecedor')}
    with op.batch_alter_table('fatura_fornecedor') as batch:
        if 'parcelas_primeiro' not in cols:
            batch.add_column(sa.Column('parcelas_primeiro', sa.Date(), nullable=True))
        if 'parcelas_intervalo' not in cols:
            batch.add_column(sa.Column('parcelas_intervalo', sa.String(), nullable=True))
        if 'parcelamento_origem' not in cols:
            batch.add_column(sa.Column('parcelamento_origem', sa.String(), nullable=True))
    if not insp.has_table('fatura_fornecedor_evento'):
        op.create_table(
            'fatura_fornecedor_evento',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
            sa.Column('fatura_id', sa.Integer(), nullable=False),
            sa.Column('acao', sa.String(), nullable=False),
            sa.Column('detalhe', sa.String(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(op.f('ix_fatura_fornecedor_evento_fazenda_id'), 'fatura_fornecedor_evento', ['fazenda_id'])
        op.create_index(op.f('ix_fatura_fornecedor_evento_fatura_id'), 'fatura_fornecedor_evento', ['fatura_id'])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('fatura_fornecedor_evento'):
        op.drop_table('fatura_fornecedor_evento')
    cols = {c['name'] for c in insp.get_columns('fatura_fornecedor')}
    with op.batch_alter_table('fatura_fornecedor') as batch:
        for nome in ('parcelamento_origem', 'parcelas_intervalo', 'parcelas_primeiro'):
            if nome in cols:
                batch.drop_column(nome)
