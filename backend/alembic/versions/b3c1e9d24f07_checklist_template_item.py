"""checklist_template_item + cronograma_sanitario_checklist_item

Fase 0, passo 3 do redesenho do evento sanitário
(docs/redesenho-evento-sanitario.md) — checklist por Ocorrência
(`CronogramaSanitario`, ver seção 1 do documento) e o cadastro do template
padrão por tipo de evento (seção 3.7.3). Migração puramente ADITIVA, sem
backfill — nenhuma linha nova em nenhuma tabela, nenhuma regra de hoje muda
de comportamento (a leitura/escrita destas duas tabelas só entra na Fase 1).

Revision ID: b3c1e9d24f07
Revises: 3f2dbf3acef1
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c1e9d24f07'
down_revision: Union[str, Sequence[str], None] = '3f2dbf3acef1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'checklist_template_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_checklist_template_item_tipo'), 'checklist_template_item', ['tipo'])
    op.create_index(op.f('ix_checklist_template_item_fazenda_id'), 'checklist_template_item', ['fazenda_id'])

    op.create_table(
        'cronograma_sanitario_checklist_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cronograma_id', sa.Integer(), nullable=False),
        sa.Column('chave', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(), nullable=False, server_default='pendente'),
        sa.Column('resposta', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('responsavel_usuario_id', sa.Integer(), nullable=True),
        sa.Column('respondido_em', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cronograma_id'], ['cronograma_sanitario.id']),
        sa.ForeignKeyConstraint(['responsavel_usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_cronograma_sanitario_checklist_item_cronograma_id'),
        'cronograma_sanitario_checklist_item', ['cronograma_id'],
    )
    op.create_index(
        op.f('ix_cronograma_sanitario_checklist_item_status'),
        'cronograma_sanitario_checklist_item', ['status'],
    )
    op.create_index(
        op.f('ix_cronograma_sanitario_checklist_item_fazenda_id'),
        'cronograma_sanitario_checklist_item', ['fazenda_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_cronograma_sanitario_checklist_item_fazenda_id'),
        table_name='cronograma_sanitario_checklist_item',
    )
    op.drop_index(
        op.f('ix_cronograma_sanitario_checklist_item_status'),
        table_name='cronograma_sanitario_checklist_item',
    )
    op.drop_index(
        op.f('ix_cronograma_sanitario_checklist_item_cronograma_id'),
        table_name='cronograma_sanitario_checklist_item',
    )
    op.drop_table('cronograma_sanitario_checklist_item')

    op.drop_index(op.f('ix_checklist_template_item_fazenda_id'), table_name='checklist_template_item')
    op.drop_index(op.f('ix_checklist_template_item_tipo'), table_name='checklist_template_item')
    op.drop_table('checklist_template_item')
