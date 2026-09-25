"""cotacao de precos com fornecedores

Novas tabelas aditivas para o módulo de Cotação de Preços com Fornecedores
(cotacao, cotacao_item, cotacao_fornecedor, cotacao_resposta,
pedido_confirmacao, fornecedor_categoria) + 3 colunas novas em `fazenda`
(inscricao_estadual, telefone, email) para os dados de faturamento enviados
ao fornecedor no "pedido formal".

Revision ID: c2c04fa7e1f3
Revises: 01ce25ba18bc
Create Date: 2026-09-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c2c04fa7e1f3'
down_revision: Union[str, Sequence[str], None] = '01ce25ba18bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente — a subida da aplicação já chama SQLModel.metadata.create_all
    # antes desta migração rodar em produção (ver f7dc02f2f302 pelo mesmo motivo).
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('cotacao'):
        op.create_table(
            'cotacao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('numero_cotacao', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('categoria', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('modo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('prazo_resposta', sa.DateTime(), nullable=False),
            sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('numero_cotacao', 'fazenda_id', name='uq_cotacao_numero_fazenda'),
        )
        op.create_index(op.f('ix_cotacao_fazenda_id'), 'cotacao', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_cotacao_numero_cotacao'), 'cotacao', ['numero_cotacao'], unique=False)

    if not insp.has_table('cotacao_item'):
        op.create_table(
            'cotacao_item',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('cotacao_id', sa.Integer(), nullable=False),
            sa.Column('estoque_id', sa.Integer(), nullable=True),
            sa.Column('produto', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('quantidade', sa.Float(), nullable=False),
            sa.Column('unidade', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.ForeignKeyConstraint(['cotacao_id'], ['cotacao.id'], ),
            sa.ForeignKeyConstraint(['estoque_id'], ['estoque.id'], ),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_cotacao_item_fazenda_id'), 'cotacao_item', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_cotacao_item_cotacao_id'), 'cotacao_item', ['cotacao_id'], unique=False)

    if not insp.has_table('cotacao_fornecedor'):
        op.create_table(
            'cotacao_fornecedor',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('cotacao_id', sa.Integer(), nullable=False),
            sa.Column('fornecedor_id', sa.Integer(), nullable=False),
            sa.Column('canal', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('token_publico', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('status_envio', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('enviado_em', sa.DateTime(), nullable=True),
            sa.Column('visualizado_em', sa.DateTime(), nullable=True),
            sa.Column('respondido_em', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['cotacao_id'], ['cotacao.id'], ),
            sa.ForeignKeyConstraint(['fornecedor_id'], ['fornecedor.id'], ),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('token_publico', name='uq_cotacao_fornecedor_token'),
        )
        op.create_index(op.f('ix_cotacao_fornecedor_fazenda_id'), 'cotacao_fornecedor', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_cotacao_fornecedor_cotacao_id'), 'cotacao_fornecedor', ['cotacao_id'], unique=False)
        op.create_index(op.f('ix_cotacao_fornecedor_token_publico'), 'cotacao_fornecedor', ['token_publico'], unique=False)

    if not insp.has_table('cotacao_resposta'):
        op.create_table(
            'cotacao_resposta',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('cotacao_fornecedor_id', sa.Integer(), nullable=False),
            sa.Column('cotacao_item_id', sa.Integer(), nullable=False),
            sa.Column('recusado', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('preco_unitario', sa.Float(), nullable=True),
            sa.Column('frete_incluso', sa.Boolean(), nullable=True),
            sa.Column('valor_frete', sa.Float(), nullable=True),
            sa.Column('prazo_entrega_dias', sa.Integer(), nullable=True),
            sa.Column('condicao_pagamento', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('vencedor', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['cotacao_fornecedor_id'], ['cotacao_fornecedor.id'], ),
            sa.ForeignKeyConstraint(['cotacao_item_id'], ['cotacao_item.id'], ),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('cotacao_fornecedor_id', 'cotacao_item_id', name='uq_cotacao_resposta_item'),
        )
        op.create_index(op.f('ix_cotacao_resposta_fazenda_id'), 'cotacao_resposta', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_cotacao_resposta_cotacao_fornecedor_id'), 'cotacao_resposta', ['cotacao_fornecedor_id'], unique=False)
        op.create_index(op.f('ix_cotacao_resposta_cotacao_item_id'), 'cotacao_resposta', ['cotacao_item_id'], unique=False)

    if not insp.has_table('pedido_confirmacao'):
        op.create_table(
            'pedido_confirmacao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('pedido_id', sa.Integer(), nullable=False),
            sa.Column('token_publico', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('previsao_entrega', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('observacao_fornecedor', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('enviado_em', sa.DateTime(), nullable=False),
            sa.Column('confirmado_em', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['pedido_id'], ['pedido.id'], ),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('token_publico', name='uq_pedido_confirmacao_token'),
        )
        op.create_index(op.f('ix_pedido_confirmacao_fazenda_id'), 'pedido_confirmacao', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_pedido_confirmacao_pedido_id'), 'pedido_confirmacao', ['pedido_id'], unique=False)
        op.create_index(op.f('ix_pedido_confirmacao_token_publico'), 'pedido_confirmacao', ['token_publico'], unique=False)

    if not insp.has_table('fornecedor_categoria'):
        op.create_table(
            'fornecedor_categoria',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('fornecedor_id', sa.Integer(), nullable=False),
            sa.Column('categoria', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.ForeignKeyConstraint(['fornecedor_id'], ['fornecedor.id'], ),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fornecedor_id', 'categoria', name='uq_fornecedor_categoria'),
        )
        op.create_index(op.f('ix_fornecedor_categoria_fazenda_id'), 'fornecedor_categoria', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_fornecedor_categoria_fornecedor_id'), 'fornecedor_categoria', ['fornecedor_id'], unique=False)

    cols_fazenda = {c['name'] for c in insp.get_columns('fazenda')}
    if 'inscricao_estadual' not in cols_fazenda:
        op.add_column('fazenda', sa.Column('inscricao_estadual', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    if 'telefone' not in cols_fazenda:
        op.add_column('fazenda', sa.Column('telefone', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    if 'email' not in cols_fazenda:
        op.add_column('fazenda', sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('fazenda', 'email')
    op.drop_column('fazenda', 'telefone')
    op.drop_column('fazenda', 'inscricao_estadual')

    op.drop_index(op.f('ix_fornecedor_categoria_fornecedor_id'), table_name='fornecedor_categoria')
    op.drop_index(op.f('ix_fornecedor_categoria_fazenda_id'), table_name='fornecedor_categoria')
    op.drop_table('fornecedor_categoria')

    op.drop_index(op.f('ix_pedido_confirmacao_token_publico'), table_name='pedido_confirmacao')
    op.drop_index(op.f('ix_pedido_confirmacao_pedido_id'), table_name='pedido_confirmacao')
    op.drop_index(op.f('ix_pedido_confirmacao_fazenda_id'), table_name='pedido_confirmacao')
    op.drop_table('pedido_confirmacao')

    op.drop_index(op.f('ix_cotacao_resposta_cotacao_item_id'), table_name='cotacao_resposta')
    op.drop_index(op.f('ix_cotacao_resposta_cotacao_fornecedor_id'), table_name='cotacao_resposta')
    op.drop_index(op.f('ix_cotacao_resposta_fazenda_id'), table_name='cotacao_resposta')
    op.drop_table('cotacao_resposta')

    op.drop_index(op.f('ix_cotacao_fornecedor_token_publico'), table_name='cotacao_fornecedor')
    op.drop_index(op.f('ix_cotacao_fornecedor_cotacao_id'), table_name='cotacao_fornecedor')
    op.drop_index(op.f('ix_cotacao_fornecedor_fazenda_id'), table_name='cotacao_fornecedor')
    op.drop_table('cotacao_fornecedor')

    op.drop_index(op.f('ix_cotacao_item_cotacao_id'), table_name='cotacao_item')
    op.drop_index(op.f('ix_cotacao_item_fazenda_id'), table_name='cotacao_item')
    op.drop_table('cotacao_item')

    op.drop_index(op.f('ix_cotacao_numero_cotacao'), table_name='cotacao')
    op.drop_index(op.f('ix_cotacao_fazenda_id'), table_name='cotacao')
    op.drop_table('cotacao')
