"""sanidade: fazenda_id em aplicações, cadastros e protocolos (não inclui Touro)

Fecha o gap do domínio Sanidade no retrofit multi-tenant: mesma coluna
aditiva (nullable, com índice) já usada em Reprodutivo/CentroCusto/Pessoa,
backfillada para a fazenda #1 (grandfathered) quando ela já existir — sem
retroatividade em nenhuma outra fazenda. `calendario_sanitario` já tinha
fazenda_id (ver c3d4e5f6a7b9) e não é tocado aqui. `touro` fica de fora de
propósito — é um catálogo genético compartilhado (provas de fornecedores
como ABS/Alta/Select Sires/CRV), não um cadastro por fazenda.

Os cadastros com nome único globalmente (principio_ativo, doenca,
exame_definicao, evento_sanitario, servico_cadastro, protocolo_sanitario,
protocolo_inducao_lactacao) trocam o unique(nome) por unique(nome,
fazenda_id), mesmo padrão de centro_custo/colostragem_bezerra — senão a 2ª
fazenda nunca conseguiria cadastrar um item com nome já usado pela 1ª.

Revision ID: c9d1e2f3a4b5
Revises: b8c9d1e2f3a4
Create Date: 2026-07-24 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, Sequence[str], None] = 'b8c9d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelas simples — só ganham a coluna aditiva (sem conflito de unicidade).
_TABELAS = [
    'sanidade',
    'aplicacao_agendada',
    'medicamento_comercial',
    'exame_resultado',
    'protocolo_sanitario_etapa',
    'protocolo_sanitario_lancamento',
    'protocolo_sanitario_aplicacao',
    'protocolo_inducao_lactacao_etapa',
    'protocolo_inducao_lancamento',
    'protocolo_inducao_medicamento',
    'protocolo_inducao_aplicacao',
]

# Cadastros com nome único globalmente — coluna aditiva + troca do
# unique(nome) por unique(nome, fazenda_id). (tabela, nome da constraint nova)
_TABELAS_NOME_UNICO = [
    ('principio_ativo', 'uq_principio_ativo_nome_fazenda'),
    ('doenca', 'uq_doenca_nome_fazenda'),
    ('exame_definicao', 'uq_exame_definicao_nome_fazenda'),
    ('evento_sanitario', 'uq_evento_sanitario_nome_fazenda'),
    ('servico_cadastro', 'uq_servico_cadastro_nome_fazenda'),
    ('protocolo_sanitario', 'uq_protocolo_sanitario_nome_fazenda'),
    ('protocolo_inducao_lactacao', 'uq_protocolo_inducao_lactacao_nome_fazenda'),
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

    for tabela, nome_constraint in _TABELAS_NOME_UNICO:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            try:
                batch_op.drop_index(f'ix_{tabela}_nome')
            except Exception:
                pass
            batch_op.create_index(f'ix_{tabela}_nome', ['nome'], unique=False)
            batch_op.create_unique_constraint(nome_constraint, ['nome', 'fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    for tabela, nome_constraint in reversed(_TABELAS_NOME_UNICO):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_constraint(nome_constraint, type_='unique')
            batch_op.drop_index(f'ix_{tabela}_nome')
            batch_op.create_index(f'ix_{tabela}_nome', ['nome'], unique=True)
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')

    for tabela in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
