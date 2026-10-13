"""preco_plano + contrato_fazenda.preco_mensal_fechado

Revision ID: b8c9d0e1f2a3
Revises: f6a7b8c9d0e1
Create Date: 2026-10-13 00:00:00.000000

Preço do plano como FATO do contrato (Plano Financeiro, fase 1.3):
- tabela `preco_plano` (catálogo de preço por plano, editável no Painel
  CowData), semeada com os preços padrão de hoje (valores copiados aqui de
  propósito — a migração não importa o código da aplicação);
- coluna `contrato_fazenda.preco_mensal_fechado` (nullable);
- backfill: contratos ATIVOS com plano de catálogo recebem o preço de catálogo
  de HOJE — nenhum valor cobrado muda.

Idempotente (has_table/has_column) e SQLite-safe.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None

# Preços padrão vigentes na data desta migração (ver PLANOS_CATALOGO).
_PRECOS_PADRAO = {
    'standard': 250.00,
    'silver': 350.00,
    'gold': 420.00,
    'diamond': 500.00,
    'financeiro': 200.00,
}


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('preco_plano'):
        op.create_table(
            'preco_plano',
            sa.Column('plano', sa.String(), nullable=False),
            sa.Column('preco', sa.Float(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=True),
            sa.Column('atualizado_por_usuario_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['atualizado_por_usuario_id'], ['usuario.id']),
            sa.PrimaryKeyConstraint('plano'),
        )

    # Semeia só o que falta (nunca sobrescreve um preço já editado).
    existentes = {r[0] for r in conn.execute(sa.text("SELECT plano FROM preco_plano")).fetchall()}
    for plano, preco in _PRECOS_PADRAO.items():
        if plano not in existentes:
            conn.execute(
                sa.text("INSERT INTO preco_plano (plano, preco, atualizado_em, atualizado_por_usuario_id) VALUES (:p, :v, NULL, NULL)"),
                {"p": plano, "v": preco},
            )

    if insp.has_table('contrato_fazenda'):
        colunas = [c['name'] for c in insp.get_columns('contrato_fazenda')]
        if 'preco_mensal_fechado' not in colunas:
            with op.batch_alter_table('contrato_fazenda') as batch:
                batch.add_column(sa.Column('preco_mensal_fechado', sa.Float(), nullable=True))
        # Contratos ativos com plano de catálogo: congela o preço de hoje.
        conn.execute(sa.text(
            "UPDATE contrato_fazenda SET preco_mensal_fechado = "
            "(SELECT preco FROM preco_plano WHERE preco_plano.plano = contrato_fazenda.plano) "
            "WHERE plano IS NOT NULL AND status = 'ativo' AND preco_mensal_fechado IS NULL"
        ))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('contrato_fazenda'):
        if 'preco_mensal_fechado' in [c['name'] for c in insp.get_columns('contrato_fazenda')]:
            with op.batch_alter_table('contrato_fazenda') as batch:
                batch.drop_column('preco_mensal_fechado')
    if insp.has_table('preco_plano'):
        op.drop_table('preco_plano')
