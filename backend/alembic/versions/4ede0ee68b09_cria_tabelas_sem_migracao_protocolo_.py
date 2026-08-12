"""cria tabelas sem migracao: protocolo_iatf/etapa, safra, diaria_auditoria, guia_folha_encargo, parametro_diaria_padrao, parametro_sugestao_movimentacao, nota_capa

Fecha o drift pré-existente relatado pela migração de backfill anterior
(029227481e9e, ver seu print "tabela(s) do model sem migração de criação"):
sete tabelas do multi-tenant existem em `fazenda/models/` e são usadas em
produção, mas nunca ganharam um `op.create_table` — só existiam porque
`SQLModel.metadata.create_all` (rede de segurança chamada na subida da
aplicação, `database.py::create_db_and_tables`) as criava por baixo dos
panos. Um banco montado só pelo Alembic (restauração, ambiente novo, réplica
de teste) nunca teria essas tabelas, e o app quebraria de forma difícil de
diagnosticar (404/500 no primeiro INSERT/SELECT).

Achamos uma oitava durante a varredura desta migração: `nota_capa` (aviso da
Capa, editável só pelo dono — fazenda/models/sistema.py::NotaCapa) tem o
mesmo drift, mas não apareceu no aviso da 029227481e9e porque aquele backfill
só varre tabelas com coluna `fazenda_id` (não é o caso — `nota_capa` é global
de propósito, sem fazenda_id: aviso da plataforma, não da fazenda).

Todas as colunas/índices/FKs/unique constraints abaixo foram conferidos
1:1 contra `SQLModel.metadata` (inspecionando um banco criado só por
`create_all`, sem nenhuma migração), não contra a leitura dos modelos — é a
fonte de verdade real do schema que já roda em produção.

Idempotente por tabela (`insp.has_table`) — precisa ser seguro em produção,
onde as sete tabelas originais já existem via `create_all` e só `nota_capa`
seria efetivamente nova.

Revision ID: 4ede0ee68b09
Revises: 029227481e9e
Create Date: 2026-08-11 22:56:45.783869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '4ede0ee68b09'
down_revision: Union[str, Sequence[str], None] = '029227481e9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('protocolo_iatf'):
        op.create_table(
            'protocolo_iatf',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome', 'fazenda_id', name='uq_protocolo_iatf_nome_fazenda'),
        )
        op.create_index(op.f('ix_protocolo_iatf_nome'), 'protocolo_iatf', ['nome'])
        op.create_index(op.f('ix_protocolo_iatf_fazenda_id'), 'protocolo_iatf', ['fazenda_id'])

    if not insp.has_table('protocolo_iatf_etapa'):
        op.create_table(
            'protocolo_iatf_etapa',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('protocolo_id', sa.Integer(), nullable=False),
            sa.Column('dia', sa.Integer(), nullable=False),
            sa.Column('criterio_tipo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('principio_ativo_id', sa.Integer(), nullable=True),
            sa.Column('produto', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('dose', sa.Float(), nullable=True),
            sa.Column('unidade', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('via', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['protocolo_id'], ['protocolo_iatf.id']),
            sa.ForeignKeyConstraint(['principio_ativo_id'], ['principio_ativo.id']),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_protocolo_iatf_etapa_protocolo_id'), 'protocolo_iatf_etapa', ['protocolo_id'])
        op.create_index(op.f('ix_protocolo_iatf_etapa_fazenda_id'), 'protocolo_iatf_etapa', ['fazenda_id'])

    if not insp.has_table('safra'):
        op.create_table(
            'safra',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('centro_custo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('data_inicio', sa.Date(), nullable=False),
            sa.Column('data_fim', sa.Date(), nullable=False),
            sa.Column('hectares', sa.Float(), nullable=False),
            sa.Column('toneladas_produzidas', sa.Float(), nullable=False),
            sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome', 'fazenda_id', name='uq_safra_nome_fazenda'),
        )
        op.create_index(op.f('ix_safra_nome'), 'safra', ['nome'])
        op.create_index(op.f('ix_safra_fazenda_id'), 'safra', ['fazenda_id'])

    if not insp.has_table('diaria_auditoria'):
        op.create_table(
            'diaria_auditoria',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('diaria_id', sa.Integer(), nullable=False),
            sa.Column('periodo_inicio', sa.Date(), nullable=False),
            sa.Column('periodo_fim', sa.Date(), nullable=False),
            sa.Column('dias_trabalhados', sa.Integer(), nullable=True),
            sa.Column('confirmado_em', sa.DateTime(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['diaria_id'], ['diaria.id']),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_diaria_auditoria_diaria_id'), 'diaria_auditoria', ['diaria_id'])
        op.create_index(op.f('ix_diaria_auditoria_fazenda_id'), 'diaria_auditoria', ['fazenda_id'])

    if not insp.has_table('guia_folha_encargo'):
        op.create_table(
            'guia_folha_encargo',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('tipo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('competencia', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('codigo_receita', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('valor_principal', sa.Float(), nullable=False),
            sa.Column('valor_multa', sa.Float(), nullable=False),
            sa.Column('valor_juros', sa.Float(), nullable=False),
            sa.Column('valor_total', sa.Float(), nullable=False),
            sa.Column('data_vencimento', sa.Date(), nullable=False),
            sa.Column('linha_digitavel', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('numero_lancamento', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('origem', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_guia_folha_encargo_fazenda_id'), 'guia_folha_encargo', ['fazenda_id'])
        op.create_index(op.f('ix_guia_folha_encargo_numero_lancamento'), 'guia_folha_encargo', ['numero_lancamento'])

    if not insp.has_table('parametro_diaria_padrao'):
        op.create_table(
            'parametro_diaria_padrao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('auditar_periodicamente', sa.Boolean(), nullable=False),
            sa.Column('frequencia_auditoria', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('dia_semana_auditoria', sa.Integer(), nullable=False),
            sa.Column('intervalo_dias_auditoria', sa.Integer(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fazenda_id', name='uq_parametro_diaria_padrao_fazenda'),
        )
        op.create_index(op.f('ix_parametro_diaria_padrao_fazenda_id'), 'parametro_diaria_padrao', ['fazenda_id'])

    if not insp.has_table('parametro_sugestao_movimentacao'):
        op.create_table(
            'parametro_sugestao_movimentacao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('modo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('dia_semana', sa.Integer(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fazenda_id', name='uq_parametro_sugestao_movimentacao_fazenda'),
        )
        op.create_index(op.f('ix_parametro_sugestao_movimentacao_fazenda_id'), 'parametro_sugestao_movimentacao', ['fazenda_id'])

    if not insp.has_table('nota_capa'):
        op.create_table(
            'nota_capa',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('titulo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('texto', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('ativa', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if insp.has_table('nota_capa'):
        op.drop_table('nota_capa')

    if insp.has_table('parametro_sugestao_movimentacao'):
        op.drop_index(op.f('ix_parametro_sugestao_movimentacao_fazenda_id'), table_name='parametro_sugestao_movimentacao')
        op.drop_table('parametro_sugestao_movimentacao')

    if insp.has_table('parametro_diaria_padrao'):
        op.drop_index(op.f('ix_parametro_diaria_padrao_fazenda_id'), table_name='parametro_diaria_padrao')
        op.drop_table('parametro_diaria_padrao')

    if insp.has_table('guia_folha_encargo'):
        op.drop_index(op.f('ix_guia_folha_encargo_numero_lancamento'), table_name='guia_folha_encargo')
        op.drop_index(op.f('ix_guia_folha_encargo_fazenda_id'), table_name='guia_folha_encargo')
        op.drop_table('guia_folha_encargo')

    if insp.has_table('diaria_auditoria'):
        op.drop_index(op.f('ix_diaria_auditoria_fazenda_id'), table_name='diaria_auditoria')
        op.drop_index(op.f('ix_diaria_auditoria_diaria_id'), table_name='diaria_auditoria')
        op.drop_table('diaria_auditoria')

    if insp.has_table('safra'):
        op.drop_index(op.f('ix_safra_fazenda_id'), table_name='safra')
        op.drop_index(op.f('ix_safra_nome'), table_name='safra')
        op.drop_table('safra')

    if insp.has_table('protocolo_iatf_etapa'):
        op.drop_index(op.f('ix_protocolo_iatf_etapa_fazenda_id'), table_name='protocolo_iatf_etapa')
        op.drop_index(op.f('ix_protocolo_iatf_etapa_protocolo_id'), table_name='protocolo_iatf_etapa')
        op.drop_table('protocolo_iatf_etapa')

    if insp.has_table('protocolo_iatf'):
        op.drop_index(op.f('ix_protocolo_iatf_fazenda_id'), table_name='protocolo_iatf')
        op.drop_index(op.f('ix_protocolo_iatf_nome'), table_name='protocolo_iatf')
        op.drop_table('protocolo_iatf')
