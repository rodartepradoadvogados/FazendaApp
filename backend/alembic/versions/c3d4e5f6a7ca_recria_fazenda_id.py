"""Recria: fazenda_id (Fase 4F)

Fecha o gap do domínio Recria (Dossiê de Desempenho Zootécnico) no retrofit
multi-tenant — mesma coluna aditiva (nullable, com índice) já usada no resto
do sistema, backfillada para a fazenda #1 (grandfathered) quando ela já
existir — sem retroatividade em nenhuma outra fazenda.

Tabelas simples (só ganham a coluna): ocorrencia_clinica (caso clínico —
transacional por fazenda), fase_recria, janela_ponto_critico,
benchmark_recria, registro_cocho (transacional por fazenda) e
categoria_manejo — todas cadastros/parâmetros editáveis pelo consultor da
fazenda (fases de idade, janelas críticas por doença, benchmark externo com
o valor da própria fazenda, categorias de manejo), por isso escopadas por
fazenda como qualquer outro cadastro, e não como vocabulário global fixo
(diferente de PrincipioAtivo/Doenca, cujo SEED de catálogo nunca ficou
escopado por fazenda — ver c9d1e2f3a4b5).

peso_alvo_idade.mes tinha unique(mes) global — vira unique(mes, fazenda_id),
mesmo padrão de tipo_servico_reprodutivo (c1d2e3f4a5b6), senão a 2ª fazenda
nunca conseguiria cadastrar a faixa de um mês já usado pela 1ª.

meta_recria era uma linha única (id=1, mesmo padrão de AlimentacaoEstado) —
vira uma linha por fazenda, com unique(fazenda_id) sozinho (não um par
campo+fazenda_id como as demais, pois a própria linha é a config "singleton"
da fazenda), mesmo padrão de parametro_diaria_padrao (a1b2c3d4e5f6).

Revision ID: c3d4e5f6a7ca
Revises: b2c3d4e5f6a2
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7ca'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelas simples — só ganham a coluna aditiva (sem conflito de unicidade).
_TABELAS = [
    'ocorrencia_clinica',
    'fase_recria',
    'janela_ponto_critico',
    'benchmark_recria',
    'registro_cocho',
    'categoria_manejo',
]

# (tabela, coluna do campo único, nome da constraint nova) — campo+fazenda_id.
_TABELAS_CAMPO_UNICO = [
    ('peso_alvo_idade', 'mes', 'uq_peso_alvo_idade_mes_fazenda'),
]

# meta_recria: unique(fazenda_id) sozinho — tratado à parte (singleton por fazenda).
_TABELA_SINGLETON = 'meta_recria'
_SINGLETON_CONSTRAINT = 'uq_meta_recria_fazenda'


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
