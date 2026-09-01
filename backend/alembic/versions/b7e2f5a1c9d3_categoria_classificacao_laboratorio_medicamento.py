"""farmácia: Laboratório, Categoria (medicamento) e Classificação do medicamento

Pedido do usuário (01/09/2026): princípio ativo, categoria e classificação do
medicamento devem poder ser cumulativos (mais de um por medicamento) — três
catálogos cadastráveis novos (mesmo padrão nome+ativo+fazenda_id de
CategoriaEstoque) + junções N:N no medicamento global (Painel CowData) e no
item de Estoque do tenant (fan-out). CategoriaMedicamento já nasce semeada
com os 7 valores hoje fixos em lib/api.ts::CLASSIFICACOES_MEDICAMENTO — só
adiciona os que ainda não existirem, idempotente.

Revision ID: b7e2f5a1c9d3
Revises: a3f1c9d8e6b4
"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2f5a1c9d3'
down_revision: Union[str, Sequence[str], None] = 'a3f1c9d8e6b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIAS_SEED = ["Antimicrobiano", "Anti-inflamatório", "Antibiótico", "Antiparasitário", "Vacina", "Hormônio", "Outro"]


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('laboratorio'):
        op.create_table(
            'laboratorio',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('nome', sa.String(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome', 'fazenda_id', name='uq_laboratorio_nome_fazenda'),
        )
        op.create_index(op.f('ix_laboratorio_fazenda_id'), 'laboratorio', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_laboratorio_nome'), 'laboratorio', ['nome'], unique=False)

    if not insp.has_table('categoria_medicamento'):
        op.create_table(
            'categoria_medicamento',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('nome', sa.String(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome', 'fazenda_id', name='uq_categoria_medicamento_nome_fazenda'),
        )
        op.create_index(op.f('ix_categoria_medicamento_fazenda_id'), 'categoria_medicamento', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_categoria_medicamento_nome'), 'categoria_medicamento', ['nome'], unique=False)

    if not insp.has_table('classificacao_medicamento_cad'):
        op.create_table(
            'classificacao_medicamento_cad',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('nome', sa.String(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome', 'fazenda_id', name='uq_classificacao_medicamento_cad_nome_fazenda'),
        )
        op.create_index(op.f('ix_classificacao_medicamento_cad_fazenda_id'), 'classificacao_medicamento_cad', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_classificacao_medicamento_cad_nome'), 'classificacao_medicamento_cad', ['nome'], unique=False)

    if not insp.has_table('medicamento_categoria'):
        op.create_table(
            'medicamento_categoria',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('medicamento_comercial_id', sa.Integer(), nullable=False),
            sa.Column('categoria_medicamento_id', sa.Integer(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['medicamento_comercial_id'], ['medicamento_comercial.id'], ),
            sa.ForeignKeyConstraint(['categoria_medicamento_id'], ['categoria_medicamento.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('medicamento_comercial_id', 'categoria_medicamento_id', name='uq_medicamento_categoria'),
        )
        op.create_index(op.f('ix_medicamento_categoria_medicamento_comercial_id'), 'medicamento_categoria', ['medicamento_comercial_id'], unique=False)
        op.create_index(op.f('ix_medicamento_categoria_categoria_medicamento_id'), 'medicamento_categoria', ['categoria_medicamento_id'], unique=False)

    if not insp.has_table('medicamento_classificacao'):
        op.create_table(
            'medicamento_classificacao',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('medicamento_comercial_id', sa.Integer(), nullable=False),
            sa.Column('classificacao_medicamento_id', sa.Integer(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['medicamento_comercial_id'], ['medicamento_comercial.id'], ),
            sa.ForeignKeyConstraint(['classificacao_medicamento_id'], ['classificacao_medicamento_cad.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('medicamento_comercial_id', 'classificacao_medicamento_id', name='uq_medicamento_classificacao'),
        )
        op.create_index(op.f('ix_medicamento_classificacao_medicamento_comercial_id'), 'medicamento_classificacao', ['medicamento_comercial_id'], unique=False)
        op.create_index(op.f('ix_medicamento_classificacao_classificacao_medicamento_id'), 'medicamento_classificacao', ['classificacao_medicamento_id'], unique=False)

    if not insp.has_table('estoque_categoria_medicamento'):
        op.create_table(
            'estoque_categoria_medicamento',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('estoque_id', sa.Integer(), nullable=False),
            sa.Column('categoria_medicamento_id', sa.Integer(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['estoque_id'], ['estoque.id'], ),
            sa.ForeignKeyConstraint(['categoria_medicamento_id'], ['categoria_medicamento.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('estoque_id', 'categoria_medicamento_id', name='uq_estoque_categoria_medicamento'),
        )
        op.create_index(op.f('ix_estoque_categoria_medicamento_estoque_id'), 'estoque_categoria_medicamento', ['estoque_id'], unique=False)
        op.create_index(op.f('ix_estoque_categoria_medicamento_categoria_medicamento_id'), 'estoque_categoria_medicamento', ['categoria_medicamento_id'], unique=False)

    if not insp.has_table('estoque_classificacao_medicamento'):
        op.create_table(
            'estoque_classificacao_medicamento',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('estoque_id', sa.Integer(), nullable=False),
            sa.Column('classificacao_medicamento_id', sa.Integer(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['estoque_id'], ['estoque.id'], ),
            sa.ForeignKeyConstraint(['classificacao_medicamento_id'], ['classificacao_medicamento_cad.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('estoque_id', 'classificacao_medicamento_id', name='uq_estoque_classificacao_medicamento'),
        )
        op.create_index(op.f('ix_estoque_classificacao_medicamento_estoque_id'), 'estoque_classificacao_medicamento', ['estoque_id'], unique=False)
        op.create_index(op.f('ix_estoque_classificacao_medicamento_classificacao_medicamento_id'), 'estoque_classificacao_medicamento', ['classificacao_medicamento_id'], unique=False)

    # Seed idempotente da CategoriaMedicamento global (fazenda_id nulo) com os
    # 7 valores hoje fixos em CLASSIFICACOES_MEDICAMENTO.
    existentes = {
        row[0] for row in conn.execute(
            sa.text("SELECT nome FROM categoria_medicamento WHERE fazenda_id IS NULL")
        ).fetchall()
    }
    agora = datetime.utcnow().isoformat(sep=' ')
    for nome in CATEGORIAS_SEED:
        if nome in existentes:
            continue
        conn.execute(
            sa.text("INSERT INTO categoria_medicamento (nome, ativo, criado_em, fazenda_id) VALUES (:nome, 1, :agora, NULL)"),
            {"nome": nome, "agora": agora},
        )


def downgrade() -> None:
    op.drop_table('estoque_classificacao_medicamento')
    op.drop_table('estoque_categoria_medicamento')
    op.drop_table('medicamento_classificacao')
    op.drop_table('medicamento_categoria')
    op.drop_table('classificacao_medicamento_cad')
    op.drop_table('categoria_medicamento')
    op.drop_table('laboratorio')
