"""Produção: fazenda_id (Fase 4F)

Adiciona fazenda_id em ControleLeiteiro, PesagemCorporal, QualidadeLeite,
EntregaLeiteMensal, Secagem e FaixaBonificacaoQualidade — os lançamentos e
cadastros de Produção (controle leiteiro, pesagem corporal, qualidade do
leite, entrega mensal, secagem e faixas de bonificação), antes 100%
single-tenant. `AgendamentoPesagem` (mesmo módulo) já tinha sido migrada à
parte (f7a8b9c0d1e2). Nenhuma das seis tabelas tem constraint única
composta hoje — só índice simples (ex.: numero_matriz) — então não é
preciso recriar unicidade, apenas adicionar a coluna aditiva de sempre.

Revision ID: c2d3e4f5a6c9
Revises: b2c3d4e5f6a2
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6c9'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABELAS = [
    'controle_leiteiro',
    'pesagem_corporal',
    'qualidade_leite',
    'entrega_leite_mensal',
    'secagem',
    'faixa_bonificacao_qualidade',
]


def upgrade() -> None:
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    for tabela in _TABELAS:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))


def downgrade() -> None:
    for tabela in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
