"""fatura de fornecedor: tabela fatura_fornecedor e conta_gerencial.fatura_id

ADITIVA e idempotente (um banco montado por SQLModel.metadata.create_all ja pode ter os objetos).

Revision ID: a8c2e6f0b417
Revises: f7b1d5a9c346
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8c2e6f0b417'
down_revision: Union[str, Sequence[str], None] = 'f7b1d5a9c346'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table('fatura_fornecedor'):
        op.create_table(
            'fatura_fornecedor',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
            sa.Column('fornecedor', sa.String(), nullable=False),
            sa.Column('rotulo', sa.String(), nullable=False),
            sa.Column('data_abertura', sa.Date(), nullable=False),
            sa.Column('data_fechamento_prevista', sa.Date(), nullable=True),
            sa.Column('data_vencimento', sa.Date(), nullable=True),
            sa.Column('conta_bancaria', sa.String(), nullable=True),
            sa.Column('centro_custo', sa.String(), nullable=True),
            sa.Column('parcelas_n', sa.Integer(), nullable=True),
            sa.Column('total_fornecedor', sa.Float(), nullable=True),
            sa.Column('valor_total', sa.Float(), nullable=True),
            sa.Column('status', sa.String(), nullable=False, server_default='aberta'),
            sa.Column('origem', sa.String(), nullable=False, server_default='fatura'),
            sa.Column('fechada_em', sa.DateTime(), nullable=True),
            sa.Column('paga_em', sa.Date(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(op.f('ix_fatura_fornecedor_fazenda_id'), 'fatura_fornecedor', ['fazenda_id'])
        op.create_index(op.f('ix_fatura_fornecedor_fornecedor'), 'fatura_fornecedor', ['fornecedor'])
    if 'fatura_id' not in {c['name'] for c in insp.get_columns('conta_gerencial')}:
        with op.batch_alter_table('conta_gerencial') as batch:
            batch.add_column(sa.Column('fatura_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_conta_gerencial_fatura_id'), 'conta_gerencial', ['fatura_id'])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if 'fatura_id' in {c['name'] for c in insp.get_columns('conta_gerencial')}:
        if 'ix_conta_gerencial_fatura_id' in {i['name'] for i in insp.get_indexes('conta_gerencial')}:
            op.drop_index('ix_conta_gerencial_fatura_id', table_name='conta_gerencial')
        with op.batch_alter_table('conta_gerencial') as batch:
            batch.drop_column('fatura_id')
    if insp.has_table('fatura_fornecedor'):
        op.drop_table('fatura_fornecedor')
