"""caixa dos funcionarios, fase 2: combinado de retencao em folha

- Tabela `caixa_retencao`: um combinado por pessoa (forma, valor, teto, vigencia,
  pausa, autorizacao marcada, revogacao).
- Coluna `caixa_movimento.folha_id`: a folha cujo pagamento gerou a retencao.

ADITIVA e idempotente (um banco montado por SQLModel.metadata.create_all ja pode
ter a tabela/coluna).

Revision ID: c4e8a2d6f913
Revises: b7d3f9a1c205
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e8a2d6f913'
down_revision: Union[str, Sequence[str], None] = 'b7d3f9a1c205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = 'caixa_retencao'


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    colunas = {c['name'] for c in insp.get_columns('caixa_movimento')}
    if 'folha_id' not in colunas:
        with op.batch_alter_table('caixa_movimento') as batch:
            batch.add_column(sa.Column('folha_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_caixa_movimento_folha_id'), 'caixa_movimento', ['folha_id'])
    if insp.has_table(TABELA):
        return
    op.create_table(
        TABELA,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
        sa.Column('pessoa_id', sa.Integer(), sa.ForeignKey('pessoa.id'), nullable=False),
        sa.Column('forma', sa.String(), nullable=False, server_default='fixo'),
        sa.Column('valor', sa.Float(), nullable=False, server_default='0'),
        sa.Column('teto', sa.Float(), nullable=True),
        sa.Column('destino', sa.String(), nullable=False, server_default='individual'),
        sa.Column('inicio', sa.Date(), nullable=False),
        sa.Column('fim', sa.Date(), nullable=True),
        sa.Column('pausada', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('autorizada', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('autorizada_em', sa.Date(), nullable=True),
        sa.Column('revogada_em', sa.Date(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.UniqueConstraint('fazenda_id', 'pessoa_id', name='uq_caixa_retencao_fazenda_pessoa'),
    )
    op.create_index(op.f('ix_caixa_retencao_fazenda_id'), TABELA, ['fazenda_id'])
    op.create_index(op.f('ix_caixa_retencao_pessoa_id'), TABELA, ['pessoa_id'])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        op.drop_table(TABELA)
    colunas = {c['name'] for c in insp.get_columns('caixa_movimento')}
    if 'folha_id' in colunas:
        with op.batch_alter_table('caixa_movimento') as batch:
            batch.drop_column('folha_id')
