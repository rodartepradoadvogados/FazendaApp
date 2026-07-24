"""financeiro: fazenda_id em Pedidos e Planejamento (Fase 3C)

Fecha o gap de Pedidos e Planejamento no retrofit multi-tenant: mesma
coluna aditiva (nullable, com índice) já usada em ContaGerencial/
PlanoContaGerencial (Fases 3A/3B — e3f4a5b6c7d8), backfillada para a
fazenda #1 (grandfathered) quando ela já existir — sem retroatividade em
nenhuma outra fazenda.

pedido.numero_pedido tem unique globalmente, mas — diferente de
numero_lancamento em ContaGerencial/LancamentoItem — não é usado como
chave de junção (PedidoItem se liga por pedido_id, uma FK de verdade), só
como rótulo de exibição. Por isso pode virar unique(numero_pedido,
fazenda_id) com segurança, mesmo padrão de plano_conta_gerencial.codigo.

orcamento_item, planejamento_cenario, planejamento_item e pedido_item não
têm campo único — só ganham a coluna aditiva.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-24 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelas simples — só ganham a coluna aditiva (sem conflito de unicidade).
_TABELAS = [
    'orcamento_item',
    'planejamento_cenario',
    'planejamento_item',
    'pedido_item',
]

# (tabela, coluna do campo único, nome da constraint nova)
_TABELAS_CAMPO_UNICO = [
    ('pedido', 'numero_pedido', 'uq_pedido_numero_pedido_fazenda'),
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    for tabela in _TABELAS:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))

    for tabela, campo, nome_constraint in _TABELAS_CAMPO_UNICO:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            try:
                batch_op.drop_index(f'ix_{tabela}_{campo}')
            except Exception:
                pass
            batch_op.create_index(f'ix_{tabela}_{campo}', [campo], unique=False)
            batch_op.create_unique_constraint(nome_constraint, [campo, 'fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    for tabela, campo, nome_constraint in reversed(_TABELAS_CAMPO_UNICO):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_constraint(nome_constraint, type_='unique')
            batch_op.drop_index(f'ix_{tabela}_{campo}')
            batch_op.create_index(f'ix_{tabela}_{campo}', [campo], unique=True)
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')

    for tabela in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
