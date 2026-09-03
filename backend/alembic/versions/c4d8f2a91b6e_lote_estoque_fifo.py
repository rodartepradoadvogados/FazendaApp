"""estoque: LoteEstoque (frascos/lotes com baixa FIFO) + MovimentoEstoque.lote_id

Fase G da Farmácia CowData (01/09/2026) — pedido do usuário: "registrar/
comprar um medicamento escolhendo um tamanho de frasco/embalagem específico
com sua própria dosagem, rastrear múltiplos lotes de tamanhos diferentes do
mesmo medicamento em estoque, e — ao aplicar — escolher explicitamente de
qual frasco/lote a dose saiu, ou, se nenhum for escolhido, baixar
automaticamente do lote mais antigo primeiro (FIFO)."

Puramente aditivo: `Estoque.quantidade` continua sendo o saldo agregado de
sempre — um item que nunca abrir um lote se comporta exatamente como antes
(ver rules/estoque_baixa.py).

Revision ID: c4d8f2a91b6e
Revises: b7e2f5a1c9d3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d8f2a91b6e'
down_revision: Union[str, Sequence[str], None] = 'b7e2f5a1c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('lote_estoque'):
        op.create_table(
            'lote_estoque',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('estoque_id', sa.Integer(), nullable=False),
            sa.Column('numero_lote', sa.String(), nullable=True),
            sa.Column('data_compra', sa.Date(), nullable=False),
            sa.Column('quantidade_comprada', sa.Float(), nullable=False),
            sa.Column('quantidade_restante', sa.Float(), nullable=False),
            sa.Column('valor_unitario', sa.Float(), nullable=True),
            sa.Column('observacao', sa.String(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['estoque_id'], ['estoque.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_lote_estoque_fazenda_id'), 'lote_estoque', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_lote_estoque_estoque_id'), 'lote_estoque', ['estoque_id'], unique=False)

    colunas_movimento = {c['name'] for c in insp.get_columns('movimento_estoque')} if insp.has_table('movimento_estoque') else set()
    if 'lote_id' not in colunas_movimento:
        # SQLite não suporta ALTER TABLE ADD CONSTRAINT direto — batch mode
        # recria a tabela por baixo dos panos (copy-and-move), mesmo padrão já
        # usado nas demais migrações que adicionam FK a uma tabela existente.
        with op.batch_alter_table('movimento_estoque', schema=None) as batch_op:
            batch_op.add_column(sa.Column('lote_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_movimento_estoque_lote_id', 'lote_estoque', ['lote_id'], ['id'])
            batch_op.create_index(op.f('ix_movimento_estoque_lote_id'), ['lote_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('movimento_estoque', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_movimento_estoque_lote_id'))
        batch_op.drop_constraint('fk_movimento_estoque_lote_id', type_='foreignkey')
        batch_op.drop_column('lote_id')
    op.drop_table('lote_estoque')
