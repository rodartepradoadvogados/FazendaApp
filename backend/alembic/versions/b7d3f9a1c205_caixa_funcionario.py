"""caixa dos funcionarios: tabela caixa_movimento (por fazenda)

Fase 1 do Caixa dos funcionarios (individual): entradas (deposito, bonificacao,
comissao, outro), retiradas com recibo e estornos. O saldo e derivado da soma
dos movimentos. Migracao ADITIVA e idempotente (um banco montado por
SQLModel.metadata.create_all ja pode ter a tabela).

Revision ID: b7d3f9a1c205
Revises: a3c9e5b71d24
Create Date: 2026-10-06 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d3f9a1c205'
down_revision: Union[str, Sequence[str], None] = 'a3c9e5b71d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = 'caixa_movimento'


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        return
    op.create_table(
        TABELA,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
        sa.Column('pessoa_id', sa.Integer(), sa.ForeignKey('pessoa.id'), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('motivo', sa.String(), nullable=False),
        sa.Column('base_valor', sa.Float(), nullable=True),
        sa.Column('percentual', sa.Float(), nullable=True),
        sa.Column('lancamento_id', sa.Integer(), sa.ForeignKey('conta_gerencial.id'), nullable=True),
        sa.Column('numero_lancamento', sa.String(), nullable=True),
        sa.Column('forma_pagamento', sa.String(), nullable=True),
        sa.Column('conta_bancaria', sa.String(), nullable=True),
        sa.Column('numero_documento_pagamento', sa.String(), nullable=True),
        sa.Column('numero_recibo', sa.String(), nullable=True),
        sa.Column('estorna_id', sa.Integer(), sa.ForeignKey('caixa_movimento.id'), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(op.f('ix_caixa_movimento_fazenda_id'), TABELA, ['fazenda_id'])
    op.create_index(op.f('ix_caixa_movimento_pessoa_id'), TABELA, ['pessoa_id'])
    op.create_index(op.f('ix_caixa_movimento_tipo'), TABELA, ['tipo'])
    op.create_index(op.f('ix_caixa_movimento_estorna_id'), TABELA, ['estorna_id'])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        op.drop_table(TABELA)
