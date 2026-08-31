"""farmacia: multi-principio ativo (N:N) + tabela de alias de mesclagem

Duas tabelas N-para-N generalizam o vínculo hoje escalar/obrigatório
`MedicamentoComercial.principio_ativo_id` / `Estoque.principio_ativo_id`
para o caso de medicamento combinado (mais de um princípio ativo na mesma
bula) — pedido do usuário (31/08/2026): "precisa poder acrescentar mais de
um princípio ativo ao medicamento, tanto no painel CowData como nos
tenants, pois hoje só pode 1". As colunas escalares NÃO são removidas (viram
o "princípio principal", sempre sincronizado com a linha `principal=True`
da tabela nova) — todo o código existente que ainda lê só o escalar continua
funcionando sem mudança.

`estoque_alias_mesclado` sustenta a mesclagem de itens de Estoque pedida
pelo usuário: quando um item "perdedor" é mesclado num "sobrevivente", o
nome antigo NUNCA é reescrito por cima do histórico (isso apagaria a
carência que valia pra aquele lançamento no passado — ver docstring de
MedicamentoComercial) — vira um alias com a carência do perdedor congelada.

Revision ID: 2e2ca0f41601
Revises: 60eb25ade4b1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '2e2ca0f41601'
down_revision: Union[str, Sequence[str], None] = '60eb25ade4b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('medicamento_principio_ativo'):
        op.create_table(
            'medicamento_principio_ativo',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('medicamento_comercial_id', sa.Integer(), nullable=False),
            sa.Column('principio_ativo_id', sa.Integer(), nullable=False),
            sa.Column('principal', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('origem_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['medicamento_comercial_id'], ['medicamento_comercial.id'], ),
            sa.ForeignKeyConstraint(['principio_ativo_id'], ['principio_ativo.id'], ),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['origem_id'], ['medicamento_principio_ativo.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('medicamento_comercial_id', 'principio_ativo_id', 'fazenda_id', name='uq_medicamento_principio_fazenda'),
        )
        op.create_index(op.f('ix_medicamento_principio_ativo_medicamento_comercial_id'), 'medicamento_principio_ativo', ['medicamento_comercial_id'], unique=False)
        op.create_index(op.f('ix_medicamento_principio_ativo_principio_ativo_id'), 'medicamento_principio_ativo', ['principio_ativo_id'], unique=False)
        op.create_index(op.f('ix_medicamento_principio_ativo_fazenda_id'), 'medicamento_principio_ativo', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_medicamento_principio_ativo_origem_id'), 'medicamento_principio_ativo', ['origem_id'], unique=False)

    if not insp.has_table('estoque_principio_ativo'):
        op.create_table(
            'estoque_principio_ativo',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('estoque_id', sa.Integer(), nullable=False),
            sa.Column('principio_ativo_id', sa.Integer(), nullable=False),
            sa.Column('principal', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['estoque_id'], ['estoque.id'], ),
            sa.ForeignKeyConstraint(['principio_ativo_id'], ['principio_ativo.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('estoque_id', 'principio_ativo_id', name='uq_estoque_principio'),
        )
        op.create_index(op.f('ix_estoque_principio_ativo_estoque_id'), 'estoque_principio_ativo', ['estoque_id'], unique=False)
        op.create_index(op.f('ix_estoque_principio_ativo_principio_ativo_id'), 'estoque_principio_ativo', ['principio_ativo_id'], unique=False)

    if not insp.has_table('estoque_alias_mesclado'):
        op.create_table(
            'estoque_alias_mesclado',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('nome_perdedor', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('estoque_perdedor_id', sa.Integer(), nullable=False),
            sa.Column('estoque_sobrevivente_id', sa.Integer(), nullable=False),
            sa.Column('carencia_leite_dias_congelada', sa.Integer(), nullable=True),
            sa.Column('carencia_carne_dias_congelada', sa.Integer(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['estoque_perdedor_id'], ['estoque.id'], ),
            sa.ForeignKeyConstraint(['estoque_sobrevivente_id'], ['estoque.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fazenda_id', 'nome_perdedor', name='uq_alias_mesclado_fazenda_nome'),
        )
        op.create_index(op.f('ix_estoque_alias_mesclado_fazenda_id'), 'estoque_alias_mesclado', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_estoque_alias_mesclado_nome_perdedor'), 'estoque_alias_mesclado', ['nome_perdedor'], unique=False)
        op.create_index(op.f('ix_estoque_alias_mesclado_estoque_perdedor_id'), 'estoque_alias_mesclado', ['estoque_perdedor_id'], unique=False)
        op.create_index(op.f('ix_estoque_alias_mesclado_estoque_sobrevivente_id'), 'estoque_alias_mesclado', ['estoque_sobrevivente_id'], unique=False)

    # Backfill: 1 linha `principal=True` na tabela nova para cada vínculo
    # escalar já existente — mantém os dois em sincronia desde o dia 1, sem
    # duplicar se a migração já rodou antes (idempotente por
    # (medicamento_comercial_id/estoque_id, principio_ativo_id)).
    conn.execute(sa.text("""
        INSERT INTO medicamento_principio_ativo (medicamento_comercial_id, principio_ativo_id, principal, criado_em, fazenda_id)
        SELECT mc.id, mc.principio_ativo_id, TRUE, CURRENT_TIMESTAMP, mc.fazenda_id
        FROM medicamento_comercial mc
        WHERE mc.principio_ativo_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM medicamento_principio_ativo mpa
              WHERE mpa.medicamento_comercial_id = mc.id AND mpa.principio_ativo_id = mc.principio_ativo_id
          )
    """))
    conn.execute(sa.text("""
        INSERT INTO estoque_principio_ativo (estoque_id, principio_ativo_id, principal, criado_em)
        SELECT e.id, e.principio_ativo_id, TRUE, CURRENT_TIMESTAMP
        FROM estoque e
        WHERE e.principio_ativo_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM estoque_principio_ativo epa
              WHERE epa.estoque_id = e.id AND epa.principio_ativo_id = e.principio_ativo_id
          )
    """))


def downgrade() -> None:
    op.drop_table('estoque_alias_mesclado')
    op.drop_table('estoque_principio_ativo')
    op.drop_table('medicamento_principio_ativo')
