"""Alimentação: fazenda_id (Fase 4C)

Fecha mais um gap do retrofit multi-tenant — o domínio de Alimentação
(cadastro de alimentos/categorias, dietas por lote, matéria seca, tabela
nutricional, análise bromatológica) nunca teve `fazenda_id`. Mesma coluna
aditiva (nullable, com índice) já usada em todo o resto do sistema,
backfillada para a fazenda #1 (grandfathered) quando ela já existir — sem
retroatividade em nenhuma outra fazenda.

categoria_alimento.nome, alimento.nome, ingrediente_ms.nome e
tabela_nutricional_produto.nome tinham unique global — viram
unique(nome, fazenda_id), mesmo padrão de tipo_pessoa (a1b2c3d4e5f6) /
tipo_servico_reprodutivo (c1d2e3f4a5b6), senão a 2ª fazenda nunca
conseguiria cadastrar um alimento/categoria/produto com o mesmo nome já
usado (ex.: "Silagem").

alimentacao_estado era uma linha única (id=1) — vira uma linha por fazenda,
com unique(fazenda_id) sozinho (mesmo caso de parametro_diaria_padrao em
a1b2c3d4e5f6), já que cada fazenda tem seu próprio ritmo de consumo e sua
própria baixa automática independente. Diferente de parametro_diaria_padrao
e diaria_auditoria, `alimentacao_estado` JÁ tinha uma migração de criação
própria (na baseline) — não precisa do guard "só altera se a tabela já
existir".

Revision ID: c1d2e3f4a5c8
Revises: b2c3d4e5f6a2
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5c8'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
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

# (tabela, coluna do campo único, nome da constraint nova) — nome+fazenda_id.
_TABELAS_CAMPO_UNICO = [
    ('categoria_alimento', 'nome', 'uq_categoria_alimento_nome_fazenda'),
    ('alimento', 'nome', 'uq_alimento_nome_fazenda'),
    ('ingrediente_ms', 'nome', 'uq_ingrediente_ms_nome_fazenda'),
    ('tabela_nutricional_produto', 'nome', 'uq_tabela_nutricional_produto_nome_fazenda'),
]

# alimentacao_estado: unique(fazenda_id) sozinho — tratado à parte.
_TABELA_SINGLETON = 'alimentacao_estado'
_SINGLETON_CONSTRAINT = 'uq_alimentacao_estado_fazenda'


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

    op.add_column(_TABELA_SINGLETON, sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f(f'ix_{_TABELA_SINGLETON}_fazenda_id'), _TABELA_SINGLETON, ['fazenda_id'], unique=False)
    if fazenda_1_existe:
        conn.execute(sa.text(f"UPDATE {_TABELA_SINGLETON} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
    with op.batch_alter_table(_TABELA_SINGLETON, schema=None) as batch_op:
        batch_op.create_unique_constraint(_SINGLETON_CONSTRAINT, ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if insp.has_table(_TABELA_SINGLETON) and _SINGLETON_CONSTRAINT in {
        c['name'] for c in insp.get_unique_constraints(_TABELA_SINGLETON)
    }:
        with op.batch_alter_table(_TABELA_SINGLETON, schema=None) as batch_op:
            batch_op.drop_constraint(_SINGLETON_CONSTRAINT, type_='unique')
        op.drop_index(op.f(f'ix_{_TABELA_SINGLETON}_fazenda_id'), table_name=_TABELA_SINGLETON)
        op.drop_column(_TABELA_SINGLETON, 'fazenda_id')

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
