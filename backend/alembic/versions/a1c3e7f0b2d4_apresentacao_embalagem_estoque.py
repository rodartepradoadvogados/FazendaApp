"""estoque: ApresentacaoEmbalagemEstoque (tamanhos de embalagem por item) + LoteEstoque.apresentacao_id

Pedido do usuário (04/09/2026): "eu quero comprar um Agrovet de 50ml e um
Agrovet de 100ml, não preciso ter que cadastrar 2 produtos" — antes disso,
cada tamanho de frasco de um medicamento precisava ser um item de `Estoque`
inteiro à parte. Esta migração cria o cadastro de tamanhos (embalagens) por
item e liga cada lote de compra (LoteEstoque, Fase G) ao tamanho de onde
veio, sem tocar em nenhum dado existente.

Revision ID: a1c3e7f0b2d4
Revises: b83734c5b8b1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c3e7f0b2d4'
down_revision: Union[str, Sequence[str], None] = 'b83734c5b8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('apresentacao_embalagem_estoque'):
        op.create_table(
            'apresentacao_embalagem_estoque',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('estoque_id', sa.Integer(), nullable=False),
            sa.Column('quantidade', sa.Float(), nullable=False),
            sa.Column('ativa', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['estoque_id'], ['estoque.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_apresentacao_embalagem_estoque_fazenda_id'), 'apresentacao_embalagem_estoque', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_apresentacao_embalagem_estoque_estoque_id'), 'apresentacao_embalagem_estoque', ['estoque_id'], unique=False)

    colunas_lote = {c['name'] for c in insp.get_columns('lote_estoque')} if insp.has_table('lote_estoque') else set()
    if 'apresentacao_id' not in colunas_lote:
        # SQLite não suporta ALTER TABLE ADD CONSTRAINT direto — batch mode
        # recria a tabela por baixo dos panos, mesmo padrão da migração que
        # adicionou MovimentoEstoque.lote_id.
        with op.batch_alter_table('lote_estoque', schema=None) as batch_op:
            batch_op.add_column(sa.Column('apresentacao_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_lote_estoque_apresentacao_id', 'apresentacao_embalagem_estoque', ['apresentacao_id'], ['id'])
            batch_op.create_index(op.f('ix_lote_estoque_apresentacao_id'), ['apresentacao_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('lote_estoque', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_lote_estoque_apresentacao_id'))
        batch_op.drop_constraint('fk_lote_estoque_apresentacao_id', type_='foreignkey')
        batch_op.drop_column('apresentacao_id')
    op.drop_table('apresentacao_embalagem_estoque')
