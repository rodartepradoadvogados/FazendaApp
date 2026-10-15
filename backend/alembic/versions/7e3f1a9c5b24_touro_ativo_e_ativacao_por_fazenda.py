"""touro_ativo_e_ativacao_por_fazenda

Revision ID: 7e3f1a9c5b24
Revises: b3ada7760c6e
Create Date: 2026-10-15 00:00:00.000000

Por que existe: a checagem semanal do catálogo NAAB passou a marcar como
INATIVO (em vez de só avisar) o touro que saiu da lista de comercializados da
NAAB — o sêmen dele ainda pode circular no mercado. `touro.ativo` é o status
global do catálogo; `touro_ativado_fazenda` guarda a decisão de uma fazenda de
usar um touro inativo mesmo assim (comprar, aplicar, selecionar), sem mexer no
catálogo das demais.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7e3f1a9c5b24'
down_revision = 'b3ada7760c6e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    colunas = {c['name'] for c in insp.get_columns('touro')}
    if 'ativo' not in colunas:
        op.add_column('touro', sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()))

    if not insp.has_table('touro_ativado_fazenda'):
        op.create_table(
            'touro_ativado_fazenda',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=False),
            sa.Column('touro_id', sa.Integer(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['touro_id'], ['touro.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fazenda_id', 'touro_id', name='uq_touro_ativado_fazenda'),
        )
        op.create_index(op.f('ix_touro_ativado_fazenda_fazenda_id'), 'touro_ativado_fazenda', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_touro_ativado_fazenda_touro_id'), 'touro_ativado_fazenda', ['touro_id'], unique=False)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('touro_ativado_fazenda'):
        op.drop_table('touro_ativado_fazenda')
    if 'ativo' in {c['name'] for c in insp.get_columns('touro')}:
        with op.batch_alter_table('touro') as batch:
            batch.drop_column('ativo')
