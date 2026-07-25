"""planos comerciais + contrato por fazenda + anexo

Revision ID: d4e5f6a7b8c0
Revises: c3d4e5f6a7b9
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c0'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Módulos comerciais contratados pela fazenda #1 (grandfathered — piloto
# real, nunca deve ficar bloqueado por esta trava nova). Preço zerado no
# backfill: não é uma cobrança de verdade, só o registro de "sempre teve
# acesso" — mesmo padrão de "aditivo, sem tocar dado real" do resto do piloto.
MODULOS_COMERCIAIS = [
    "rebanho", "reprodutivo", "produtivo", "sanitario", "financeiro",
    "planejamento", "pedidos", "estoque", "alimentacao", "agricultura", "consultor",
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'preco_modulo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('modulo', sa.String(), nullable=False),
        sa.Column('preco', sa.Float(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_preco_modulo_modulo'), 'preco_modulo', ['modulo'], unique=True)

    op.create_table(
        'contrato_fazenda',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('plano', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('aprovado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('data_fechamento', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['aprovado_por_usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contrato_fazenda_fazenda_id'), 'contrato_fazenda', ['fazenda_id'], unique=True)

    op.create_table(
        'contrato_fazenda_modulo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('modulo', sa.String(), nullable=False),
        sa.Column('preco', sa.Float(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fazenda_id', 'modulo', name='uq_contrato_fazenda_modulo'),
    )
    op.create_index(op.f('ix_contrato_fazenda_modulo_fazenda_id'), 'contrato_fazenda_modulo', ['fazenda_id'], unique=False)
    op.create_index(op.f('ix_contrato_fazenda_modulo_modulo'), 'contrato_fazenda_modulo', ['modulo'], unique=False)

    op.create_table(
        'contrato_anexo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('nome_arquivo', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
        sa.Column('conteudo', sa.LargeBinary(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contrato_anexo_fazenda_id'), 'contrato_anexo', ['fazenda_id'], unique=False)

    conn = op.get_bind()
    now = sa.func.now()

    # Catálogo de preço-padrão por módulo — zerado, você edita depois (tela
    # de admin) para os contratos "sob medida" (os 4 planos fechados têm
    # preço próprio no PLANOS_CATALOGO em código, não vêm deste catálogo).
    for modulo in MODULOS_COMERCIAIS:
        conn.execute(
            sa.text("INSERT INTO preco_modulo (modulo, preco, atualizado_em) VALUES (:m, 0.0, :now)"),
            {"m": modulo, "now": conn.execute(sa.text("SELECT CURRENT_TIMESTAMP")).scalar()},
        )

    # Fazenda #1 (piloto real) — grandfathered: contrato já ATIVO, todos os
    # módulos comerciais, sem passar pela tela de aprovação. Preço 0 no
    # backfill (não é uma cobrança nova, é só registrar o que já valia).
    fazenda_1 = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()
    if fazenda_1:
        agora = conn.execute(sa.text("SELECT CURRENT_TIMESTAMP")).scalar()
        conn.execute(
            sa.text(
                "INSERT INTO contrato_fazenda (fazenda_id, plano, status, data_fechamento, criado_em, atualizado_em) "
                "VALUES (1, NULL, 'ativo', :agora, :agora, :agora)"
            ),
            {"agora": agora},
        )
        for modulo in MODULOS_COMERCIAIS:
            conn.execute(
                sa.text(
                    "INSERT INTO contrato_fazenda_modulo (fazenda_id, modulo, preco, ativo, criado_em) "
                    "VALUES (1, :m, 0.0, true, :agora)"
                ),
                {"m": modulo, "agora": agora},
            )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_contrato_anexo_fazenda_id'), table_name='contrato_anexo')
    op.drop_table('contrato_anexo')

    op.drop_index(op.f('ix_contrato_fazenda_modulo_modulo'), table_name='contrato_fazenda_modulo')
    op.drop_index(op.f('ix_contrato_fazenda_modulo_fazenda_id'), table_name='contrato_fazenda_modulo')
    op.drop_table('contrato_fazenda_modulo')

    op.drop_index(op.f('ix_contrato_fazenda_fazenda_id'), table_name='contrato_fazenda')
    op.drop_table('contrato_fazenda')

    op.drop_index(op.f('ix_preco_modulo_modulo'), table_name='preco_modulo')
    op.drop_table('preco_modulo')
