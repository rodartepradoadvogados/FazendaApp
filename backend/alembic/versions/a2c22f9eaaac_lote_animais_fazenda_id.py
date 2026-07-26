"""animais/lote: fazenda_id em Lote e demais tabelas do domínio ainda sem a coluna

Fecha o gap do domínio Animais/Lote no retrofit multi-tenant — só `Animal`
tinha `fazenda_id` (ver f1a2b3c4d5e6/piloto original); `Lote` e as demais 10
tabelas deste arquivo de modelo ficaram de fora até agora. Mesma coluna
aditiva (nullable, com índice) já usada em Sanidade/Reprodutivo/Financeiro/
Pessoal, backfillada para a fazenda #1 (grandfathered) quando ela já existir
— sem retroatividade em nenhuma outra fazenda.

`Lote.codigo`, `MotivoBaixa.nome`, `MotivoVenda.nome`, `Raca.nome`,
`GrauSangue.nome` e `MotivoMovimentacao.nome` (únicos globalmente) trocam
para unique(campo, fazenda_id) — mesmo padrão de Sanidade (c9d1e2f3a4b5) —
senão a 2ª fazenda nunca conseguiria cadastrar um lote/motivo/raça com
código ou nome já usado pela 1ª.

`MovimentoLote`, `BaixaAnimal`, `CompraAnimal`, `VendaAnimal` e
`ComissaoCorretagem` são só coluna aditiva, sem constraint a ajustar.

`ParametroSugestaoMovimentacao` (configuração singleton, id=1 — mesmo padrão
que `ParametroDiariaPadrao` tinha antes de ser de-singletonizado na Fase 4B,
PR #304) fica de fora de propósito — precisa do mesmo tipo de redesenho antes
de fazer sentido ganhar a coluna. `Touro` (banco de dados genético
compartilhado) também fica de fora, mesma razão documentada em c9d1e2f3a4b5.

Revision ID: a2c22f9eaaac
Revises: 2a7d86fb27f5
Create Date: 2026-07-26 00:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2c22f9eaaac'
down_revision: Union[str, Sequence[str], None] = '2a7d86fb27f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelas simples — só ganham a coluna aditiva (sem conflito de unicidade).
_TABELAS = [
    'movimento_lote',
    'baixa_animal',
    'compra_animal',
    'venda_animal',
    'comissao_corretagem',
]

# Cadastros com campo único globalmente — coluna aditiva + troca da unique
# constraint por (campo, fazenda_id). (tabela, campo, nome do índice antigo, nome da constraint nova)
_TABELAS_UNICAS = [
    ('lote', 'codigo', 'ix_lote_codigo', 'uq_lote_codigo_fazenda'),
    ('motivo_baixa', 'nome', 'ix_motivo_baixa_nome', 'uq_motivo_baixa_nome_fazenda'),
    ('motivo_venda', 'nome', 'ix_motivo_venda_nome', 'uq_motivo_venda_nome_fazenda'),
    ('raca', 'nome', 'ix_raca_nome', 'uq_raca_nome_fazenda'),
    ('grau_sangue_cadastro', 'nome', 'ix_grau_sangue_cadastro_nome', 'uq_grau_sangue_nome_fazenda'),
    ('motivo_movimentacao', 'nome', 'ix_motivo_movimentacao_nome', 'uq_motivo_movimentacao_nome_fazenda'),
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

    for tabela, campo, indice_antigo, nome_constraint in _TABELAS_UNICAS:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            try:
                batch_op.drop_index(indice_antigo)
            except Exception:
                pass
            batch_op.create_index(indice_antigo, [campo], unique=False)
            batch_op.create_unique_constraint(nome_constraint, [campo, 'fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    for tabela, campo, indice_antigo, nome_constraint in reversed(_TABELAS_UNICAS):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_constraint(nome_constraint, type_='unique')
            batch_op.drop_index(indice_antigo)
            batch_op.create_index(indice_antigo, [campo], unique=True)
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')

    for tabela in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
