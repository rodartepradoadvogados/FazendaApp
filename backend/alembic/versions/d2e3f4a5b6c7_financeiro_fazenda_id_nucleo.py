"""financeiro: fazenda_id no núcleo (conta_gerencial, lancamento_item, lancamento_anexo)

Fase 3A do retrofit multi-tenant no domínio Financeiro: mesma coluna aditiva
(nullable, com índice) já usada em Reprodutivo/Sanidade/ContaCorrente/
CentroCusto, backfillada para a fazenda #1 (grandfathered) quando ela já
existir — sem retroatividade em nenhuma outra fazenda.

Escopo desta migração: só as 3 tabelas do NÚCLEO de lançamento (a conta
gerencial em si, os itens de produto/serviço e os anexos) — nenhuma delas tem
nome/código único globalmente, então não há troca de unique constraint aqui
(diferente do padrão de CentroCusto/Sanidade). PlanoContaGerencial,
TipoDocumento, FormaPagamentoCadastro, Pedido, OrcamentoItem,
PlanejamentoCenario/Item, Patrimonio, ManutencaoPatrimonio e CurvaABC ficam
para as próximas fases (3B/3C/3D) — ver tasks #665-#667.

Revision ID: d2e3f4a5b6c7
Revises: c9d1e2f3a4b5
Create Date: 2026-07-24 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c9d1e2f3a4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABELAS = [
    'conta_gerencial',
    'lancamento_item',
    'lancamento_anexo',
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


def downgrade() -> None:
    """Downgrade schema."""
    for tabela in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
