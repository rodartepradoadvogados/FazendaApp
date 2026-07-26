"""alimentacao: fazenda_id nas 10 tabelas do domínio (exceto o singleton AlimentacaoEstado)

Fecha o gap do domínio Alimentação no retrofit multi-tenant. Mesma coluna
aditiva (nullable, com índice) já usada em Sanidade/Reprodutivo/Financeiro/
Pessoal/Animais/Lote/Estoque, backfillada para a fazenda #1 (grandfathered)
quando ela já existir — sem retroatividade em nenhuma outra fazenda.

`CategoriaAlimento.nome`, `Alimento.nome`, `IngredienteMS.nome` e
`TabelaNutricionalProduto.nome` (únicos globalmente) trocam para
unique(nome, fazenda_id) — mesmo padrão de Sanidade (c9d1e2f3a4b5).

`AlimentacaoEstado` (configuração singleton, id=1, mesmo padrão de
`ParametroDiariaPadrao`) fica de fora de propósito — precisa de um
redesenho maior antes de fazer sentido ganhar a coluna; ver proposta de
separação fazenda/empresa, Parte 1.6.

Revision ID: efc2b9a74f51
Revises: 69f803f7f860
Create Date: 2026-07-26 00:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efc2b9a74f51'
down_revision: Union[str, Sequence[str], None] = '69f803f7f860'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelas simples — só ganham a coluna aditiva (sem conflito de unicidade).
_TABELAS = [
    'dieta',
    'dieta_lancamento',
    'dieta_item_programado',
    'tabela_nutricional_valor',
    'analise_bromatologica',
    'dieta_registro_real',
]

# Cadastros com nome único globalmente — coluna aditiva + troca do
# unique(nome) por unique(nome, fazenda_id). (tabela, nome do índice antigo, nome da constraint nova)
_TABELAS_UNICAS = [
    ('categoria_alimento', 'ix_categoria_alimento_nome', 'uq_categoria_alimento_nome_fazenda'),
    ('alimento', 'ix_alimento_nome', 'uq_alimento_nome_fazenda'),
    ('ingrediente_ms', 'ix_ingrediente_ms_nome', 'uq_ingrediente_ms_nome_fazenda'),
    ('tabela_nutricional_produto', 'ix_tabela_nutricional_produto_nome', 'uq_tabela_nutricional_produto_nome_fazenda'),
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

    for tabela, indice_antigo, nome_constraint in _TABELAS_UNICAS:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            try:
                batch_op.drop_index(indice_antigo)
            except Exception:
                pass
            batch_op.create_index(indice_antigo, ['nome'], unique=False)
            batch_op.create_unique_constraint(nome_constraint, ['nome', 'fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    for tabela, indice_antigo, nome_constraint in reversed(_TABELAS_UNICAS):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_constraint(nome_constraint, type_='unique')
            batch_op.drop_index(indice_antigo)
            batch_op.create_index(indice_antigo, ['nome'], unique=True)
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')

    for tabela in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
