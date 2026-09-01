"""formulação: estoque_id em AlimentoNutricional/TabelaNutricionalProduto/DietaSimulacaoItem + produto_nome

Fase 2 do plano de correção de Alimentação (01/09/2026) — pedido do usuário:
"Importar do cadastro" deve permitir escolher, dentro de uma família de
Alimento (ex.: Concentrado Protéico), qual produto de Estoque específico
está sendo importado — hoje a composição só existe no nível de família,
então produtos com composição cadastrada na Tabela Nutricional (por
produto comercial) nunca chegam à simulação de dieta.

Puramente aditivo: `estoque_id` nulo em qualquer uma das 3 tabelas mantém o
comportamento de hoje (entrada/linha em nível de família). A unicidade de
`AlimentoNutricional` passa a incluir `estoque_id` para permitir múltiplas
composições por família, uma por produto.

Revision ID: d3f8a1c96e02
Revises: c4d8f2a91b6e
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3f8a1c96e02'
down_revision: Union[str, Sequence[str], None] = 'c4d8f2a91b6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas_an = {c['name'] for c in insp.get_columns('alimento_nutricional')}
    if 'estoque_id' not in colunas_an:
        with op.batch_alter_table('alimento_nutricional', schema=None) as batch_op:
            batch_op.add_column(sa.Column('estoque_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_alimento_nutricional_estoque_id', 'estoque', ['estoque_id'], ['id'])
            batch_op.create_index(op.f('ix_alimento_nutricional_estoque_id'), ['estoque_id'], unique=False)
            batch_op.drop_constraint('uq_alimento_nutricional_alimento_fazenda', type_='unique')
            batch_op.create_unique_constraint(
                'uq_alimento_nutricional_alimento_estoque_fazenda',
                ['alimento_id', 'estoque_id', 'fazenda_id'],
            )

    colunas_tnp = {c['name'] for c in insp.get_columns('tabela_nutricional_produto')}
    if 'estoque_id' not in colunas_tnp:
        with op.batch_alter_table('tabela_nutricional_produto', schema=None) as batch_op:
            batch_op.add_column(sa.Column('estoque_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_tabela_nutricional_produto_estoque_id', 'estoque', ['estoque_id'], ['id'])
            batch_op.create_index(op.f('ix_tabela_nutricional_produto_estoque_id'), ['estoque_id'], unique=False)

    colunas_dsi = {c['name'] for c in insp.get_columns('dieta_simulacao_item')}
    if 'estoque_id' not in colunas_dsi:
        with op.batch_alter_table('dieta_simulacao_item', schema=None) as batch_op:
            batch_op.add_column(sa.Column('estoque_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_dieta_simulacao_item_estoque_id', 'estoque', ['estoque_id'], ['id'])
    if 'produto_nome' not in colunas_dsi:
        with op.batch_alter_table('dieta_simulacao_item', schema=None) as batch_op:
            batch_op.add_column(sa.Column('produto_nome', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('dieta_simulacao_item', schema=None) as batch_op:
        batch_op.drop_column('produto_nome')
        batch_op.drop_constraint('fk_dieta_simulacao_item_estoque_id', type_='foreignkey')
        batch_op.drop_column('estoque_id')

    with op.batch_alter_table('tabela_nutricional_produto', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_tabela_nutricional_produto_estoque_id'))
        batch_op.drop_constraint('fk_tabela_nutricional_produto_estoque_id', type_='foreignkey')
        batch_op.drop_column('estoque_id')

    with op.batch_alter_table('alimento_nutricional', schema=None) as batch_op:
        batch_op.drop_constraint('uq_alimento_nutricional_alimento_estoque_fazenda', type_='unique')
        batch_op.create_unique_constraint(
            'uq_alimento_nutricional_alimento_fazenda',
            ['alimento_id', 'fazenda_id'],
        )
        batch_op.drop_index(op.f('ix_alimento_nutricional_estoque_id'))
        batch_op.drop_constraint('fk_alimento_nutricional_estoque_id', type_='foreignkey')
        batch_op.drop_column('estoque_id')
