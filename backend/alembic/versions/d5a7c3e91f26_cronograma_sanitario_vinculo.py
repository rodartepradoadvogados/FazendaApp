"""vinculo financeiro/compras do agendamento preventivo

Fatia 9 do planejamento unificado (docs/agents/auditoria-preventivo-agenda/
planejamento/06-planejamento-unificado.md, secao 7). Migracao ADITIVA (uma
tabela nova), sem backfill:

  cronograma_sanitario_vinculo -- liga o agendamento a um pagamento ja
      realizado, a uma conta a pagar, a uma cotacao ou a um pedido (tipo +
      alvo_id), com quem criou/encerrou, quando e por que.

Idempotente: um banco montado por SQLModel.metadata.create_all ja pode ter a
tabela (mesmo padrao de c4e8a1f7b352).

Revision ID: d5a7c3e91f26
Revises: c4e8a1f7b352
Create Date: 2026-09-30 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5a7c3e91f26'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1f7b352'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = 'cronograma_sanitario_vinculo'


def upgrade() -> None:
    """Upgrade schema. Idempotente."""
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        return
    op.create_table(
        TABELA,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
        sa.Column('cronograma_id', sa.Integer(), sa.ForeignKey('cronograma_sanitario.id'), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('alvo_id', sa.Integer(), nullable=False),
        sa.Column('numero_lancamento', sa.String(), nullable=True),
        sa.Column('estado', sa.String(), nullable=False, server_default='ativo'),
        sa.Column('valor', sa.Float(), nullable=True),
        sa.Column('modo', sa.String(), nullable=True),
        sa.Column('subtipo', sa.String(), nullable=True),
        sa.Column('rotulo', sa.String(), nullable=True),
        sa.Column('descricao', sa.String(), nullable=True),
        sa.Column('vencimento', sa.Date(), nullable=True),
        sa.Column('criado_por_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('encerrado_por_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('encerrado_em', sa.DateTime(), nullable=True),
        sa.Column('motivo_encerramento', sa.String(), nullable=True),
    )
    op.create_index(op.f('ix_cronograma_sanitario_vinculo_fazenda_id'), TABELA, ['fazenda_id'])
    op.create_index(op.f('ix_cronograma_sanitario_vinculo_cronograma_id'), TABELA, ['cronograma_id'])
    op.create_index(op.f('ix_cronograma_sanitario_vinculo_tipo'), TABELA, ['tipo'])
    op.create_index(op.f('ix_cronograma_sanitario_vinculo_alvo_id'), TABELA, ['alvo_id'])
    op.create_index(op.f('ix_cronograma_sanitario_vinculo_estado'), TABELA, ['estado'])


def downgrade() -> None:
    """Downgrade schema."""
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        op.drop_table(TABELA)
