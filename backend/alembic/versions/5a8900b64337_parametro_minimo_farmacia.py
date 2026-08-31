"""farmacia: estoque minimo por fazenda em unidade de medida (nao em frascos)

Nova tabela `parametro_minimo_farmacia` — mínimo de um princípio ativo em
`unidade_base` (ml/L/g/unidade), específico de cada fazenda. Pedido do
usuário (31/08/2026): "estoque mínimo... tem que ser em unidade de medida.
Ex.: Sincrogest — 3 pacotes de 10 + 2 pacotes de 5 — mínimo: 12 unidades, e
não pacotes."

Puramente ADITIVA — não toca em `principio_ativo` nem em nenhuma linha já
lançada. Sem uma linha aqui, `rules.farmacia.resumo_principios` continua
usando a regra antiga (mínimo em número de apresentações/frascos,
`PrincipioAtivo.estoque_minimo_apresentacoes`) — nenhum dado existente muda
de comportamento sozinho; cada fazenda concilia o próprio mínimo pelo
Painel de Conciliação (Configurações > Cadastro > Farmácia > Estoque
mínimo), um princípio de cada vez.

Revision ID: 5a8900b64337
Revises: 2e2ca0f41601
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5a8900b64337'
down_revision: Union[str, Sequence[str], None] = '2e2ca0f41601'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('parametro_minimo_farmacia'):
        op.create_table(
            'parametro_minimo_farmacia',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=False),
            sa.Column('principio_ativo_id', sa.Integer(), nullable=False),
            sa.Column('estoque_minimo_base', sa.Float(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['principio_ativo_id'], ['principio_ativo.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fazenda_id', 'principio_ativo_id', name='uq_minimo_fazenda_principio'),
        )
        op.create_index(op.f('ix_parametro_minimo_farmacia_fazenda_id'), 'parametro_minimo_farmacia', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_parametro_minimo_farmacia_principio_ativo_id'), 'parametro_minimo_farmacia', ['principio_ativo_id'], unique=False)


def downgrade() -> None:
    op.drop_table('parametro_minimo_farmacia')
