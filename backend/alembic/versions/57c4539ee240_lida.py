"""lida: tarefas gerais da fazenda por período ou frequência

Molde (lida) + etapa (lida_etapa, modo "periodo") + lançamento
(lida_lancamento) + aplicação (lida_aplicacao) — mesma arquitetura de 4
camadas do protocolo customizado. Ver fazenda/models/lida.py.

Revision ID: c3d4e5f6a7b8
Revises: b7e4c92f1a08
Create Date: 2026-08-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57c4539ee240'
down_revision: Union[str, Sequence[str], None] = 'b7e4c92f1a08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'lida',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('modo', sa.String(), nullable=False),
        sa.Column('dia_inicial', sa.Integer(), nullable=False),
        sa.Column('frequencia_dias', sa.Integer(), nullable=True),
        sa.Column('descricao_evento', sa.String(), nullable=True),
        sa.Column('insumo_padrao', sa.String(), nullable=True),
        sa.Column('insumo_dose', sa.Float(), nullable=True),
        sa.Column('insumo_unidade', sa.String(), nullable=True),
        sa.Column('foto_obrigatoria', sa.Boolean(), nullable=False),
        sa.Column('dar_baixa_estoque', sa.Boolean(), nullable=False),
        sa.Column('vincular_financeiro', sa.Boolean(), nullable=False),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nome', 'fazenda_id', name='uq_lida_nome_fazenda'),
    )
    op.create_index(op.f('ix_lida_nome'), 'lida', ['nome'])
    op.create_index(op.f('ix_lida_fazenda_id'), 'lida', ['fazenda_id'])

    op.create_table(
        'lida_etapa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lida_id', sa.Integer(), nullable=False),
        sa.Column('dia_inicio', sa.Integer(), nullable=False),
        sa.Column('dia_fim', sa.Integer(), nullable=True),
        sa.Column('descricao_evento', sa.String(), nullable=False),
        sa.Column('insumo_padrao', sa.String(), nullable=True),
        sa.Column('insumo_dose', sa.Float(), nullable=True),
        sa.Column('insumo_unidade', sa.String(), nullable=True),
        sa.Column('foto_obrigatoria', sa.Boolean(), nullable=False),
        sa.Column('ordem', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['lida_id'], ['lida.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lida_etapa_lida_id'), 'lida_etapa', ['lida_id'])
    op.create_index(op.f('ix_lida_etapa_fazenda_id'), 'lida_etapa', ['fazenda_id'])

    op.create_table(
        'lida_lancamento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lida_id', sa.Integer(), nullable=False),
        sa.Column('nome_protocolo', sa.String(), nullable=False),
        sa.Column('modo', sa.String(), nullable=False),
        sa.Column('dia_inicial', sa.Integer(), nullable=False),
        sa.Column('data_inicio', sa.Date(), nullable=False),
        sa.Column('alvo_tipo', sa.String(), nullable=False),
        sa.Column('lote', sa.String(), nullable=True),
        sa.Column('responsavel', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('encerrado_em', sa.Date(), nullable=True),
        sa.Column('encerrado_motivo', sa.String(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['lida_id'], ['lida.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lida_lancamento_lida_id'), 'lida_lancamento', ['lida_id'])
    op.create_index(op.f('ix_lida_lancamento_data_inicio'), 'lida_lancamento', ['data_inicio'])
    op.create_index(op.f('ix_lida_lancamento_ativo'), 'lida_lancamento', ['ativo'])
    op.create_index(op.f('ix_lida_lancamento_fazenda_id'), 'lida_lancamento', ['fazenda_id'])

    op.create_table(
        'lida_aplicacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lancamento_id', sa.Integer(), nullable=False),
        sa.Column('numero_matriz', sa.String(), nullable=True),
        sa.Column('dia', sa.Integer(), nullable=False),
        sa.Column('descricao', sa.String(), nullable=False),
        sa.Column('insumo', sa.String(), nullable=True),
        sa.Column('insumo_dose', sa.Float(), nullable=True),
        sa.Column('insumo_unidade', sa.String(), nullable=True),
        sa.Column('foto_obrigatoria', sa.Boolean(), nullable=False),
        sa.Column('foto_url', sa.String(), nullable=True),
        sa.Column('data_prevista', sa.Date(), nullable=False),
        sa.Column('realizada', sa.Boolean(), nullable=False),
        sa.Column('data_realizacao', sa.Date(), nullable=True),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['lancamento_id'], ['lida_lancamento.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lida_aplicacao_lancamento_id'), 'lida_aplicacao', ['lancamento_id'])
    op.create_index(op.f('ix_lida_aplicacao_numero_matriz'), 'lida_aplicacao', ['numero_matriz'])
    op.create_index(op.f('ix_lida_aplicacao_data_prevista'), 'lida_aplicacao', ['data_prevista'])
    op.create_index(op.f('ix_lida_aplicacao_realizada'), 'lida_aplicacao', ['realizada'])
    op.create_index(op.f('ix_lida_aplicacao_fazenda_id'), 'lida_aplicacao', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lida_aplicacao_fazenda_id'), table_name='lida_aplicacao')
    op.drop_index(op.f('ix_lida_aplicacao_realizada'), table_name='lida_aplicacao')
    op.drop_index(op.f('ix_lida_aplicacao_data_prevista'), table_name='lida_aplicacao')
    op.drop_index(op.f('ix_lida_aplicacao_numero_matriz'), table_name='lida_aplicacao')
    op.drop_index(op.f('ix_lida_aplicacao_lancamento_id'), table_name='lida_aplicacao')
    op.drop_table('lida_aplicacao')

    op.drop_index(op.f('ix_lida_lancamento_fazenda_id'), table_name='lida_lancamento')
    op.drop_index(op.f('ix_lida_lancamento_ativo'), table_name='lida_lancamento')
    op.drop_index(op.f('ix_lida_lancamento_data_inicio'), table_name='lida_lancamento')
    op.drop_index(op.f('ix_lida_lancamento_lida_id'), table_name='lida_lancamento')
    op.drop_table('lida_lancamento')

    op.drop_index(op.f('ix_lida_etapa_fazenda_id'), table_name='lida_etapa')
    op.drop_index(op.f('ix_lida_etapa_lida_id'), table_name='lida_etapa')
    op.drop_table('lida_etapa')

    op.drop_index(op.f('ix_lida_fazenda_id'), table_name='lida')
    op.drop_index(op.f('ix_lida_nome'), table_name='lida')
    op.drop_table('lida')
