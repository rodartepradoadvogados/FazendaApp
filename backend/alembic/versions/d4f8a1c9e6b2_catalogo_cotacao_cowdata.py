"""catalogo e cotacao cowdata

Novas tabelas aditivas para o catálogo de preços de referência do Painel
CowData (classificacao_cowdata, finalidade_cowdata, fornecedor_cowdata +
duas tabelas N:N de classificação/finalidade do fornecedor, produto_padrao +
N:N de finalidade, cotacao_cowdata/item/fornecedor/resposta,
preco_base_sugerido + participante de média) — SEM fazenda_id em nenhuma
delas, de propósito (catálogo único da CowData, não um catálogo global
"visível" por fazenda como farmácia; ver docstring de
fazenda/models/catalogo_cowdata.py). Mais 2 colunas novas: `fazenda.
mostrar_precos_referencia_cowdata` (opt-out por fazenda) e
`permissao_equipe_cowdata.pode_editar_cotacoes` (a nova área "cotacoes" do
Painel CowData).

Semeia classificacao_cowdata com o mesmo vocabulário inicial de
rules.categorias.CATEGORIAS_FORNECEDOR (9 valores), só para a tela não
nascer vazia — continua editável depois pelo Painel CowData.

Revision ID: d4f8a1c9e6b2
Revises: c2c04fa7e1f3
Create Date: 2026-09-25 21:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd4f8a1c9e6b2'
down_revision: Union[str, Sequence[str], None] = 'c2c04fa7e1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mesmo vocabulário de rules.categorias.CATEGORIAS_FORNECEDOR — inlined
# (migração nunca importa código da aplicação, mesmo padrão já usado em
# b3c1e9d24f07).
_CLASSIFICACOES_SEED = [
    "Ração e insumos alimentares",
    "Sêmen e genética",
    "Medicamentos e produtos veterinários",
    "Equipamentos e manutenção",
    "Combustível e transporte",
    "Serviços veterinários/técnicos",
    "Energia e utilidades",
    "Embalagens e materiais",
    "Outros",
]


def upgrade() -> None:
    # Idempotente — a subida da aplicação já chama SQLModel.metadata.create_all
    # antes desta migração rodar em produção (mesmo motivo de c2c04fa7e1f3).
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('classificacao_cowdata'):
        op.create_table(
            'classificacao_cowdata',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome'),
        )
        op.create_index(op.f('ix_classificacao_cowdata_nome'), 'classificacao_cowdata', ['nome'])

    if not insp.has_table('finalidade_cowdata'):
        op.create_table(
            'finalidade_cowdata',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome'),
        )
        op.create_index(op.f('ix_finalidade_cowdata_nome'), 'finalidade_cowdata', ['nome'])

    if not insp.has_table('fornecedor_cowdata'):
        op.create_table(
            'fornecedor_cowdata',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('cnpj_cpf', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('telefone', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('observacoes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_fornecedor_cowdata_nome'), 'fornecedor_cowdata', ['nome'])

    if not insp.has_table('fornecedor_cowdata_classificacao'):
        op.create_table(
            'fornecedor_cowdata_classificacao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fornecedor_cowdata_id', sa.Integer(), nullable=False),
            sa.Column('classificacao_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['fornecedor_cowdata_id'], ['fornecedor_cowdata.id']),
            sa.ForeignKeyConstraint(['classificacao_id'], ['classificacao_cowdata.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fornecedor_cowdata_id', 'classificacao_id', name='uq_forncd_classificacao'),
        )
        op.create_index(op.f('ix_fornecedor_cowdata_classificacao_fornecedor_cowdata_id'), 'fornecedor_cowdata_classificacao', ['fornecedor_cowdata_id'])
        op.create_index(op.f('ix_fornecedor_cowdata_classificacao_classificacao_id'), 'fornecedor_cowdata_classificacao', ['classificacao_id'])

    if not insp.has_table('fornecedor_cowdata_finalidade'):
        op.create_table(
            'fornecedor_cowdata_finalidade',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fornecedor_cowdata_id', sa.Integer(), nullable=False),
            sa.Column('finalidade_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['fornecedor_cowdata_id'], ['fornecedor_cowdata.id']),
            sa.ForeignKeyConstraint(['finalidade_id'], ['finalidade_cowdata.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fornecedor_cowdata_id', 'finalidade_id', name='uq_forncd_finalidade'),
        )
        op.create_index(op.f('ix_fornecedor_cowdata_finalidade_fornecedor_cowdata_id'), 'fornecedor_cowdata_finalidade', ['fornecedor_cowdata_id'])
        op.create_index(op.f('ix_fornecedor_cowdata_finalidade_finalidade_id'), 'fornecedor_cowdata_finalidade', ['finalidade_id'])

    if not insp.has_table('produto_padrao'):
        op.create_table(
            'produto_padrao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('unidade', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('classificacao_id', sa.Integer(), nullable=True),
            sa.Column('medicamento_comercial_id', sa.Integer(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['classificacao_id'], ['classificacao_cowdata.id']),
            sa.ForeignKeyConstraint(['medicamento_comercial_id'], ['medicamento_comercial.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_produto_padrao_nome'), 'produto_padrao', ['nome'])
        op.create_index(op.f('ix_produto_padrao_classificacao_id'), 'produto_padrao', ['classificacao_id'])
        op.create_index(op.f('ix_produto_padrao_medicamento_comercial_id'), 'produto_padrao', ['medicamento_comercial_id'])

    if not insp.has_table('produto_padrao_finalidade'):
        op.create_table(
            'produto_padrao_finalidade',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('produto_padrao_id', sa.Integer(), nullable=False),
            sa.Column('finalidade_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['produto_padrao_id'], ['produto_padrao.id']),
            sa.ForeignKeyConstraint(['finalidade_id'], ['finalidade_cowdata.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('produto_padrao_id', 'finalidade_id', name='uq_produtopadrao_finalidade'),
        )
        op.create_index(op.f('ix_produto_padrao_finalidade_produto_padrao_id'), 'produto_padrao_finalidade', ['produto_padrao_id'])
        op.create_index(op.f('ix_produto_padrao_finalidade_finalidade_id'), 'produto_padrao_finalidade', ['finalidade_id'])

    if not insp.has_table('cotacao_cowdata'):
        op.create_table(
            'cotacao_cowdata',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('titulo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='rascunho'),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.Column('fechada_em', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if not insp.has_table('cotacao_cowdata_fornecedor'):
        op.create_table(
            'cotacao_cowdata_fornecedor',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('cotacao_cowdata_id', sa.Integer(), nullable=False),
            sa.Column('fornecedor_cowdata_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['cotacao_cowdata_id'], ['cotacao_cowdata.id']),
            sa.ForeignKeyConstraint(['fornecedor_cowdata_id'], ['fornecedor_cowdata.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('cotacao_cowdata_id', 'fornecedor_cowdata_id', name='uq_cotcd_fornecedor'),
        )
        op.create_index(op.f('ix_cotacao_cowdata_fornecedor_cotacao_cowdata_id'), 'cotacao_cowdata_fornecedor', ['cotacao_cowdata_id'])
        op.create_index(op.f('ix_cotacao_cowdata_fornecedor_fornecedor_cowdata_id'), 'cotacao_cowdata_fornecedor', ['fornecedor_cowdata_id'])

    if not insp.has_table('cotacao_cowdata_item'):
        op.create_table(
            'cotacao_cowdata_item',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('cotacao_cowdata_id', sa.Integer(), nullable=False),
            sa.Column('modo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('produto_padrao_id', sa.Integer(), nullable=True),
            sa.Column('classificacao_id', sa.Integer(), nullable=True),
            sa.Column('finalidade_id', sa.Integer(), nullable=True),
            sa.Column('descricao_livre', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.ForeignKeyConstraint(['cotacao_cowdata_id'], ['cotacao_cowdata.id']),
            sa.ForeignKeyConstraint(['produto_padrao_id'], ['produto_padrao.id']),
            sa.ForeignKeyConstraint(['classificacao_id'], ['classificacao_cowdata.id']),
            sa.ForeignKeyConstraint(['finalidade_id'], ['finalidade_cowdata.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_cotacao_cowdata_item_cotacao_cowdata_id'), 'cotacao_cowdata_item', ['cotacao_cowdata_id'])
        op.create_index(op.f('ix_cotacao_cowdata_item_produto_padrao_id'), 'cotacao_cowdata_item', ['produto_padrao_id'])
        op.create_index(op.f('ix_cotacao_cowdata_item_classificacao_id'), 'cotacao_cowdata_item', ['classificacao_id'])
        op.create_index(op.f('ix_cotacao_cowdata_item_finalidade_id'), 'cotacao_cowdata_item', ['finalidade_id'])

    if not insp.has_table('cotacao_cowdata_resposta'):
        op.create_table(
            'cotacao_cowdata_resposta',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('cotacao_cowdata_item_id', sa.Integer(), nullable=False),
            sa.Column('fornecedor_cowdata_id', sa.Integer(), nullable=False),
            sa.Column('valor', sa.Float(), nullable=True),
            sa.Column('condicao_pagamento', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('prazo_entrega_dias', sa.Integer(), nullable=True),
            sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('recusado', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('registrado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['cotacao_cowdata_item_id'], ['cotacao_cowdata_item.id']),
            sa.ForeignKeyConstraint(['fornecedor_cowdata_id'], ['fornecedor_cowdata.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('cotacao_cowdata_item_id', 'fornecedor_cowdata_id', name='uq_cotcd_resposta'),
        )
        op.create_index(op.f('ix_cotacao_cowdata_resposta_cotacao_cowdata_item_id'), 'cotacao_cowdata_resposta', ['cotacao_cowdata_item_id'])
        op.create_index(op.f('ix_cotacao_cowdata_resposta_fornecedor_cowdata_id'), 'cotacao_cowdata_resposta', ['fornecedor_cowdata_id'])

    if not insp.has_table('preco_base_sugerido'):
        op.create_table(
            'preco_base_sugerido',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('produto_padrao_id', sa.Integer(), nullable=False),
            sa.Column('valor', sa.Float(), nullable=False),
            sa.Column('unidade', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('regiao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('origem', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='manual'),
            sa.Column('cotacao_cowdata_item_id', sa.Integer(), nullable=True),
            sa.Column('fornecedor_escolhido_id', sa.Integer(), nullable=True),
            sa.Column('eh_media', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('publicado', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('publicado_em', sa.DateTime(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('atribuido_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['produto_padrao_id'], ['produto_padrao.id']),
            sa.ForeignKeyConstraint(['cotacao_cowdata_item_id'], ['cotacao_cowdata_item.id']),
            sa.ForeignKeyConstraint(['fornecedor_escolhido_id'], ['fornecedor_cowdata.id']),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_preco_base_sugerido_produto_padrao_id'), 'preco_base_sugerido', ['produto_padrao_id'])
        op.create_index(op.f('ix_preco_base_sugerido_cotacao_cowdata_item_id'), 'preco_base_sugerido', ['cotacao_cowdata_item_id'])

    if not insp.has_table('preco_base_sugerido_participante_media'):
        op.create_table(
            'preco_base_sugerido_participante_media',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('preco_base_sugerido_id', sa.Integer(), nullable=False),
            sa.Column('fornecedor_cowdata_id', sa.Integer(), nullable=False),
            sa.Column('valor_informado', sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(['preco_base_sugerido_id'], ['preco_base_sugerido.id']),
            sa.ForeignKeyConstraint(['fornecedor_cowdata_id'], ['fornecedor_cowdata.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_preco_base_sugerido_participante_media_preco_base_sugerido_id'), 'preco_base_sugerido_participante_media', ['preco_base_sugerido_id'])

    cols_fazenda = {c['name'] for c in insp.get_columns('fazenda')}
    if 'mostrar_precos_referencia_cowdata' not in cols_fazenda:
        op.add_column('fazenda', sa.Column('mostrar_precos_referencia_cowdata', sa.Boolean(), nullable=False, server_default=sa.true()))

    cols_permissao = {c['name'] for c in insp.get_columns('permissao_equipe_cowdata')}
    if 'pode_editar_cotacoes' not in cols_permissao:
        op.add_column('permissao_equipe_cowdata', sa.Column('pode_editar_cotacoes', sa.Boolean(), nullable=False, server_default=sa.false()))

    # Seed condicionado a "tabela vazia" (mesmo padrão de b3c1e9d24f07) — não
    # duplica numa 2ª chamada, e ainda semeia se a tabela já existia (via
    # create_all) mas sem linhas.
    ja_tem_classificacao = conn.execute(sa.text("SELECT 1 FROM classificacao_cowdata LIMIT 1")).first()
    if not ja_tem_classificacao:
        classificacao_cowdata = sa.table(
            'classificacao_cowdata',
            sa.column('nome', sa.String()), sa.column('ativo', sa.Boolean()), sa.column('criado_em', sa.DateTime()),
        )
        agora = datetime.utcnow()
        op.bulk_insert(classificacao_cowdata, [
            {"nome": nome, "ativo": True, "criado_em": agora} for nome in _CLASSIFICACOES_SEED
        ])


def downgrade() -> None:
    op.drop_column('permissao_equipe_cowdata', 'pode_editar_cotacoes')
    op.drop_column('fazenda', 'mostrar_precos_referencia_cowdata')
    op.drop_table('preco_base_sugerido_participante_media')
    op.drop_table('preco_base_sugerido')
    op.drop_table('cotacao_cowdata_resposta')
    op.drop_table('cotacao_cowdata_item')
    op.drop_table('cotacao_cowdata_fornecedor')
    op.drop_table('cotacao_cowdata')
    op.drop_table('produto_padrao_finalidade')
    op.drop_table('produto_padrao')
    op.drop_table('fornecedor_cowdata_finalidade')
    op.drop_table('fornecedor_cowdata_classificacao')
    op.drop_table('fornecedor_cowdata')
    op.drop_table('finalidade_cowdata')
    op.drop_table('classificacao_cowdata')
