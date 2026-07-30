"""protocolo_customizado: motor de protocolos configurável pelo usuário
(catálogo + etapas + lançamento + aplicações que viram eventos na Agenda)

Ver fazenda/models/protocolo_customizado.py e
fazenda/rules/protocolo_customizado.py.

Também resolve as duas heads abertas em main (029dcd895d43 do filtro salvo e
a merge 7478fd686e77 de fotos do campo) — esta revisão é o novo ponto único
de convergência.

Revision ID: e93e3302df29
Revises: 029dcd895d43, 7478fd686e77
Create Date: 2026-07-29 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e93e3302df29'
down_revision: Union[str, Sequence[str], None] = ('029dcd895d43', '7478fd686e77')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'protocolo_customizado',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('categoria', sa.String(), nullable=False),
        sa.Column('dia_inicial', sa.Integer(), nullable=False),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_protocolo_customizado_nome'), 'protocolo_customizado', ['nome'])
    op.create_index(op.f('ix_protocolo_customizado_fazenda_id'), 'protocolo_customizado', ['fazenda_id'])
    op.create_index(
        'uq_protocolo_customizado_nome_fazenda', 'protocolo_customizado', ['nome', 'fazenda_id'], unique=True,
    )

    op.create_table(
        'protocolo_customizado_etapa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('protocolo_id', sa.Integer(), nullable=False),
        sa.Column('dia', sa.Integer(), nullable=False),
        sa.Column('descricao_evento', sa.String(), nullable=False),
        sa.Column('insumo_padrao', sa.String(), nullable=True),
        sa.Column('dose', sa.Float(), nullable=True),
        sa.Column('unidade', sa.String(), nullable=True),
        sa.Column('via', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('ordem', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['protocolo_id'], ['protocolo_customizado.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_protocolo_customizado_etapa_protocolo_id'), 'protocolo_customizado_etapa', ['protocolo_id'])
    op.create_index(op.f('ix_protocolo_customizado_etapa_fazenda_id'), 'protocolo_customizado_etapa', ['fazenda_id'])

    op.create_table(
        'protocolo_customizado_lancamento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('protocolo_id', sa.Integer(), nullable=False),
        sa.Column('nome_protocolo', sa.String(), nullable=False),
        sa.Column('categoria', sa.String(), nullable=False),
        sa.Column('dia_inicial', sa.Integer(), nullable=False),
        sa.Column('data_inicio', sa.Date(), nullable=False),
        sa.Column('lote', sa.String(), nullable=True),
        sa.Column('responsavel', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['protocolo_id'], ['protocolo_customizado.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_protocolo_customizado_lancamento_protocolo_id'), 'protocolo_customizado_lancamento', ['protocolo_id'])
    op.create_index(op.f('ix_protocolo_customizado_lancamento_data_inicio'), 'protocolo_customizado_lancamento', ['data_inicio'])
    op.create_index(op.f('ix_protocolo_customizado_lancamento_ativo'), 'protocolo_customizado_lancamento', ['ativo'])
    op.create_index(op.f('ix_protocolo_customizado_lancamento_fazenda_id'), 'protocolo_customizado_lancamento', ['fazenda_id'])

    op.create_table(
        'protocolo_customizado_aplicacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lancamento_id', sa.Integer(), nullable=False),
        sa.Column('numero_matriz', sa.String(), nullable=True),
        sa.Column('dia', sa.Integer(), nullable=False),
        sa.Column('descricao', sa.String(), nullable=False),
        sa.Column('insumo', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('data_prevista', sa.Date(), nullable=False),
        sa.Column('realizada', sa.Boolean(), nullable=False),
        sa.Column('data_realizacao', sa.Date(), nullable=True),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['lancamento_id'], ['protocolo_customizado_lancamento.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_protocolo_customizado_aplicacao_lancamento_id'), 'protocolo_customizado_aplicacao', ['lancamento_id'])
    op.create_index(op.f('ix_protocolo_customizado_aplicacao_numero_matriz'), 'protocolo_customizado_aplicacao', ['numero_matriz'])
    op.create_index(op.f('ix_protocolo_customizado_aplicacao_data_prevista'), 'protocolo_customizado_aplicacao', ['data_prevista'])
    op.create_index(op.f('ix_protocolo_customizado_aplicacao_realizada'), 'protocolo_customizado_aplicacao', ['realizada'])
    op.create_index(op.f('ix_protocolo_customizado_aplicacao_fazenda_id'), 'protocolo_customizado_aplicacao', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_protocolo_customizado_aplicacao_fazenda_id'), table_name='protocolo_customizado_aplicacao')
    op.drop_index(op.f('ix_protocolo_customizado_aplicacao_realizada'), table_name='protocolo_customizado_aplicacao')
    op.drop_index(op.f('ix_protocolo_customizado_aplicacao_data_prevista'), table_name='protocolo_customizado_aplicacao')
    op.drop_index(op.f('ix_protocolo_customizado_aplicacao_numero_matriz'), table_name='protocolo_customizado_aplicacao')
    op.drop_index(op.f('ix_protocolo_customizado_aplicacao_lancamento_id'), table_name='protocolo_customizado_aplicacao')
    op.drop_table('protocolo_customizado_aplicacao')

    op.drop_index(op.f('ix_protocolo_customizado_lancamento_fazenda_id'), table_name='protocolo_customizado_lancamento')
    op.drop_index(op.f('ix_protocolo_customizado_lancamento_ativo'), table_name='protocolo_customizado_lancamento')
    op.drop_index(op.f('ix_protocolo_customizado_lancamento_data_inicio'), table_name='protocolo_customizado_lancamento')
    op.drop_index(op.f('ix_protocolo_customizado_lancamento_protocolo_id'), table_name='protocolo_customizado_lancamento')
    op.drop_table('protocolo_customizado_lancamento')

    op.drop_index(op.f('ix_protocolo_customizado_etapa_fazenda_id'), table_name='protocolo_customizado_etapa')
    op.drop_index(op.f('ix_protocolo_customizado_etapa_protocolo_id'), table_name='protocolo_customizado_etapa')
    op.drop_table('protocolo_customizado_etapa')

    op.drop_index('uq_protocolo_customizado_nome_fazenda', table_name='protocolo_customizado')
    op.drop_index(op.f('ix_protocolo_customizado_fazenda_id'), table_name='protocolo_customizado')
    op.drop_index(op.f('ix_protocolo_customizado_nome'), table_name='protocolo_customizado')
    op.drop_table('protocolo_customizado')
