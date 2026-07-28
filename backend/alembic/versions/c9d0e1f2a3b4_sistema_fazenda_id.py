"""sistema: fazenda_id em AgendaManual, EventoRealizado, SolicitacaoExclusao,
LancamentoPendente, PortalMensagem (Fase 0 — domínio Sistema)

Fecha o gap "Sistema (5 tabelas)" do retrofit multi-tenant: essas 5 tabelas
não tinham fazenda_id nenhum, nem no schema nem em nenhuma query — vazamento
total (dado de uma fazenda visível/gerenciável por qualquer outra). Mesma
coluna aditiva (nullable, com índice) já usada em Reprodutivo/Produção/
Sanidade/CentroCusto/Pessoa, backfillada para a fazenda #1 (grandfathered)
quando ela já existir.

evento_realizado também troca o unique(evento_id) sozinho por
unique(evento_id, fazenda_id) — evento_id é um hash de campos como número do
animal, que não é único entre fazendas diferentes, então o unique antigo
podia fazer uma fazenda "roubar" a marcação de concluído de outra.

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-07-28 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELAS = ['agenda_manual', 'evento_realizado', 'solicitacao_exclusao', 'lancamento_pendente', 'portal_mensagem']


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    for tabela in _TABELAS:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))

    # evento_realizado: troca o ÍNDICE único de evento_id sozinho (era
    # Field(unique=True) -> UNIQUE INDEX no SQLite, não uma constraint
    # nomeada) pelo par (evento_id, fazenda_id).
    op.drop_index('ix_evento_realizado_evento_id', table_name='evento_realizado')
    op.create_index('uq_evento_realizado_evento_fazenda', 'evento_realizado', ['evento_id', 'fazenda_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_evento_realizado_evento_fazenda', table_name='evento_realizado')
    op.create_index('ix_evento_realizado_evento_id', 'evento_realizado', ['evento_id'], unique=True)

    for tabela in _TABELAS:
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
