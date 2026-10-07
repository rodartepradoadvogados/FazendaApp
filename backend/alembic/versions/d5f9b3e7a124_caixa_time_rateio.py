"""caixa dos funcionarios, fase 3: caixa do time e rateio do PL

Tabelas `caixa_time`, `caixa_time_membro`, `caixa_time_movimento`, `caixa_rateio`,
`caixa_rateio_linha` e a coluna `caixa_movimento.rateio_id`. ADITIVA e idempotente.

Revision ID: d5f9b3e7a124
Revises: c4e8a2d6f913
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5f9b3e7a124'
down_revision: Union[str, Sequence[str], None] = 'c4e8a2d6f913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_FAZ = lambda: sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True)  # noqa: E731


def _criar(insp, nome, *colunas, indices=()):
    if insp.has_table(nome):
        return
    op.create_table(nome, *colunas)
    for col in indices:
        op.create_index(op.f(f'ix_{nome}_{col}'), nome, [col])


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if 'rateio_id' not in {c['name'] for c in insp.get_columns('caixa_movimento')}:
        with op.batch_alter_table('caixa_movimento') as batch:
            batch.add_column(sa.Column('rateio_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_caixa_movimento_rateio_id'), 'caixa_movimento', ['rateio_id'])

    _criar(insp, 'caixa_time',
           sa.Column('id', sa.Integer(), primary_key=True), FK_FAZ(),
           sa.Column('nome', sa.String(), nullable=False),
           sa.Column('auto_tipos', sa.String(), nullable=False, server_default=''),
           sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
           sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
           indices=('fazenda_id',))
    _criar(insp, 'caixa_time_membro',
           sa.Column('id', sa.Integer(), primary_key=True), FK_FAZ(),
           sa.Column('time_id', sa.Integer(), sa.ForeignKey('caixa_time.id'), nullable=False),
           sa.Column('pessoa_id', sa.Integer(), sa.ForeignKey('pessoa.id'), nullable=False),
           sa.Column('entrada', sa.Date(), nullable=False),
           sa.Column('saida', sa.Date(), nullable=True),
           sa.UniqueConstraint('time_id', 'pessoa_id', name='uq_caixa_time_membro'),
           indices=('fazenda_id', 'time_id', 'pessoa_id'))
    _criar(insp, 'caixa_time_movimento',
           sa.Column('id', sa.Integer(), primary_key=True), FK_FAZ(),
           sa.Column('time_id', sa.Integer(), sa.ForeignKey('caixa_time.id'), nullable=False),
           sa.Column('tipo', sa.String(), nullable=False),
           sa.Column('valor', sa.Float(), nullable=False),
           sa.Column('data', sa.Date(), nullable=False),
           sa.Column('motivo', sa.String(), nullable=False),
           sa.Column('lancamento_id', sa.Integer(), sa.ForeignKey('conta_gerencial.id'), nullable=True),
           sa.Column('numero_lancamento', sa.String(), nullable=True),
           sa.Column('rateio_id', sa.Integer(), nullable=True),
           sa.Column('estorna_id', sa.Integer(), sa.ForeignKey('caixa_time_movimento.id'), nullable=True),
           sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
           sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
           indices=('fazenda_id', 'time_id', 'tipo', 'rateio_id', 'estorna_id'))
    _criar(insp, 'caixa_rateio',
           sa.Column('id', sa.Integer(), primary_key=True), FK_FAZ(),
           sa.Column('time_id', sa.Integer(), sa.ForeignKey('caixa_time.id'), nullable=False),
           sa.Column('periodo_inicio', sa.Date(), nullable=False),
           sa.Column('periodo_fim', sa.Date(), nullable=False),
           sa.Column('data_entrega', sa.Date(), nullable=False),
           sa.Column('total', sa.Float(), nullable=False, server_default='0'),
           sa.Column('situacao', sa.String(), nullable=False, server_default='rascunho'),
           sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
           sa.Column('confirmado_em', sa.DateTime(), nullable=True),
           sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
           indices=('fazenda_id', 'time_id'))
    _criar(insp, 'caixa_rateio_linha',
           sa.Column('id', sa.Integer(), primary_key=True), FK_FAZ(),
           sa.Column('rateio_id', sa.Integer(), sa.ForeignKey('caixa_rateio.id'), nullable=False),
           sa.Column('pessoa_id', sa.Integer(), sa.ForeignKey('pessoa.id'), nullable=False),
           sa.Column('dias', sa.Integer(), nullable=False, server_default='0'),
           sa.Column('parte_calculada', sa.Float(), nullable=False, server_default='0'),
           sa.Column('penalidade_pct', sa.Float(), nullable=False, server_default='0'),
           sa.Column('penalidade_motivo', sa.String(), nullable=True),
           sa.Column('documento_anexo_id', sa.Integer(), nullable=True),
           sa.Column('parte_final', sa.Float(), nullable=False, server_default='0'),
           sa.Column('destino', sa.String(), nullable=False, server_default='individual'),
           sa.Column('forma_pagamento', sa.String(), nullable=True),
           sa.Column('movimento_id', sa.Integer(), nullable=True),
           sa.Column('retirada_id', sa.Integer(), nullable=True),
           sa.UniqueConstraint('rateio_id', 'pessoa_id', name='uq_caixa_rateio_linha'),
           indices=('fazenda_id', 'rateio_id', 'pessoa_id'))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for nome in ('caixa_rateio_linha', 'caixa_rateio', 'caixa_time_movimento', 'caixa_time_membro', 'caixa_time'):
        if insp.has_table(nome):
            op.drop_table(nome)
    if 'rateio_id' in {c['name'] for c in insp.get_columns('caixa_movimento')}:
        with op.batch_alter_table('caixa_movimento') as batch:
            batch.drop_column('rateio_id')
