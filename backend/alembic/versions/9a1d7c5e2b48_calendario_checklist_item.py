"""calendario_sanitario_checklist_item

Fase 2, passo 10 do redesenho do evento sanitário
(docs/redesenho-evento-sanitario.md, seção 3.7.0 — passo 4 "Checklist" do
wizard novo de Cadastro). Checklist customizado por REGRA
(`CalendarioSanitario`) — distinto do template por tipo
(`ChecklistTemplateItem`, seção 3.7.3) e do checklist por Ocorrência já
materializada (`ChecklistItem`/`cronograma_sanitario_checklist_item`, Fase 0).
Migração ADITIVA — tabela nasce vazia; toda regra já cadastrada continua
usando o template do tipo dinamicamente (nenhuma regra de hoje muda de
comportamento) até ser salva de novo pelo wizard novo.

Revision ID: 9a1d7c5e2b48
Revises: 22ee4f2f2cf7
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1d7c5e2b48'
down_revision: Union[str, Sequence[str], None] = '22ee4f2f2cf7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotente por tabela (`insp.has_table`, mesmo padrão de 4ede0ee68b09
    # e b3c1e9d24f07) — precisa ser seguro quando a tabela já existe via
    # `SQLModel.metadata.create_all` (rede de segurança da subida da app),
    # cenário coberto por tests/test_migracao_tabelas_faltantes.py.
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table('calendario_sanitario_checklist_item'):
        return

    op.create_table(
        'calendario_sanitario_checklist_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calendario_sanitario_id', sa.Integer(), nullable=False),
        sa.Column('chave', sa.String(), nullable=False, server_default='custom'),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['calendario_sanitario_id'], ['calendario_sanitario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_calendario_sanitario_checklist_item_calendario_sanitario_id'),
        'calendario_sanitario_checklist_item', ['calendario_sanitario_id'],
    )
    op.create_index(
        op.f('ix_calendario_sanitario_checklist_item_fazenda_id'),
        'calendario_sanitario_checklist_item', ['fazenda_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_calendario_sanitario_checklist_item_fazenda_id'),
        table_name='calendario_sanitario_checklist_item',
    )
    op.drop_index(
        op.f('ix_calendario_sanitario_checklist_item_calendario_sanitario_id'),
        table_name='calendario_sanitario_checklist_item',
    )
    op.drop_table('calendario_sanitario_checklist_item')
