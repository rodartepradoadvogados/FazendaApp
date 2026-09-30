"""configuracao da deteccao de cio de repasse (por fazenda)

Fatia 10 do planejamento unificado (docs/agents/auditoria-preventivo-agenda/
planejamento/06-planejamento-unificado.md, decisao 10). Migracao ADITIVA (uma
tabela nova), sem backfill: fazenda sem linha continua no comportamento legado
(ligado, 14 dias, todas as inseminacoes, com aviso na Agenda).

  repasse_config -- usar ou nao, produto vinculado (item de estoque da
      categoria "Detecção de cio de repasse"), 1a checagem (dias apos o
      servico), repeticao, indicacao na Agenda e quem entra
      (todas | iatf | monta_natural). Uma linha por fazenda.

Idempotente: um banco montado por SQLModel.metadata.create_all ja pode ter a
tabela (mesmo padrao de d5a7c3e91f26).

Revision ID: f1b6d2a8c904
Revises: e7b3a9d4c1f8
Create Date: 2026-09-30 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b6d2a8c904'
down_revision: Union[str, Sequence[str], None] = 'e7b3a9d4c1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = 'repasse_config'


def upgrade() -> None:
    """Upgrade schema. Idempotente."""
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        return
    op.create_table(
        TABELA,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
        sa.Column('usar', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('estoque_id', sa.Integer(), sa.ForeignKey('estoque.id'), nullable=True),
        sa.Column('dias_apos_servico', sa.Integer(), nullable=False, server_default='14'),
        sa.Column('repetir', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('repetir_cada_dias', sa.Integer(), nullable=False, server_default='21'),
        sa.Column('repeticoes', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('mostrar_na_agenda', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('quem_entra', sa.String(), nullable=False, server_default='todas'),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_por_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.UniqueConstraint('fazenda_id', name='uq_repasse_config_fazenda'),
    )
    op.create_index(op.f('ix_repasse_config_fazenda_id'), TABELA, ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        op.drop_table(TABELA)
