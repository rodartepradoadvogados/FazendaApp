"""cronograma_sanitario

Workflow dinâmico de acompanhamento do calendário sanitário: uma regra
(CalendarioSanitario) marcada `usa_cronograma=True` passa a gerar, por
ocorrência, um CronogramaSanitario — a lista de animais que bateram o
critério (CronogramaSanitarioAnimal) mais a decisão de execução (veterinário
agendado / aplicação própria / ainda em branco). Ver
fazenda/rules/cronograma_sanitario.py.

Revision ID: 97d68401d5b0
Revises: a1c9f3d8b422
Create Date: 2026-08-02 13:21:37.509710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '97d68401d5b0'
down_revision: Union[str, Sequence[str], None] = 'a1c9f3d8b422'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('calendario_sanitario', sa.Column('usa_cronograma', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        'cronograma_sanitario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calendario_sanitario_id', sa.Integer(), nullable=False),
        sa.Column('data_evento', sa.Date(), nullable=False),
        sa.Column('data_original', sa.Date(), nullable=True),
        sa.Column('modo_execucao', sa.String(), nullable=True),
        sa.Column('veterinario_pessoa_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='aberto'),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.Column('concluido_em', sa.DateTime(), nullable=True),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['calendario_sanitario_id'], ['calendario_sanitario.id']),
        sa.ForeignKeyConstraint(['veterinario_pessoa_id'], ['pessoa.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cronograma_sanitario_calendario_sanitario_id'), 'cronograma_sanitario', ['calendario_sanitario_id'])
    op.create_index(op.f('ix_cronograma_sanitario_status'), 'cronograma_sanitario', ['status'])
    op.create_index(op.f('ix_cronograma_sanitario_fazenda_id'), 'cronograma_sanitario', ['fazenda_id'])

    op.create_table(
        'cronograma_sanitario_animal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cronograma_id', sa.Integer(), nullable=False),
        sa.Column('numero_matriz', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='sugerido'),
        sa.Column('data_sugestao', sa.Date(), nullable=False),
        sa.Column('data_decisao', sa.Date(), nullable=True),
        sa.Column('data_aplicacao', sa.Date(), nullable=True),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cronograma_id'], ['cronograma_sanitario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cronograma_sanitario_animal_cronograma_id'), 'cronograma_sanitario_animal', ['cronograma_id'])
    op.create_index(op.f('ix_cronograma_sanitario_animal_numero_matriz'), 'cronograma_sanitario_animal', ['numero_matriz'])
    op.create_index(op.f('ix_cronograma_sanitario_animal_status'), 'cronograma_sanitario_animal', ['status'])
    op.create_index(op.f('ix_cronograma_sanitario_animal_fazenda_id'), 'cronograma_sanitario_animal', ['fazenda_id'])
    op.create_index(
        'uq_cronograma_animal', 'cronograma_sanitario_animal', ['cronograma_id', 'numero_matriz'], unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_cronograma_animal', table_name='cronograma_sanitario_animal')
    op.drop_index(op.f('ix_cronograma_sanitario_animal_fazenda_id'), table_name='cronograma_sanitario_animal')
    op.drop_index(op.f('ix_cronograma_sanitario_animal_status'), table_name='cronograma_sanitario_animal')
    op.drop_index(op.f('ix_cronograma_sanitario_animal_numero_matriz'), table_name='cronograma_sanitario_animal')
    op.drop_index(op.f('ix_cronograma_sanitario_animal_cronograma_id'), table_name='cronograma_sanitario_animal')
    op.drop_table('cronograma_sanitario_animal')

    op.drop_index(op.f('ix_cronograma_sanitario_fazenda_id'), table_name='cronograma_sanitario')
    op.drop_index(op.f('ix_cronograma_sanitario_status'), table_name='cronograma_sanitario')
    op.drop_index(op.f('ix_cronograma_sanitario_calendario_sanitario_id'), table_name='cronograma_sanitario')
    op.drop_table('cronograma_sanitario')

    op.drop_column('calendario_sanitario', 'usa_cronograma')
