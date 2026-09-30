"""rotina automatica da lista de espera (por fazenda)

Docs: docs/agents/auditoria-preventivo-agenda/planejamento/11-rotina-lista-de-espera.md.
Migracao ADITIVA, sem backfill (nada muda de comportamento: a rotina so atua
quando a fazenda a liga em Parametros):

  calendario_sanitario.dias_antecedencia_lista_espera -- opcional; NULL = vale o
      valor unico da fazenda (Parametros);
  rotina_lista_espera_estado -- uma linha por fazenda: ultima execucao, ultimo
      aviso do card diario e lock/idempotencia entre instancias.

Idempotente: um banco montado por SQLModel.metadata.create_all ja pode ter a
coluna/tabela (mesmo padrao de f1b6d2a8c904).

Revision ID: a3c9e5b71d24
Revises: f1b6d2a8c904
Create Date: 2026-09-30 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c9e5b71d24'
down_revision: Union[str, Sequence[str], None] = 'f1b6d2a8c904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = 'rotina_lista_espera_estado'


def upgrade() -> None:
    """Upgrade schema. Idempotente."""
    insp = sa.inspect(op.get_bind())
    colunas = {c['name'] for c in insp.get_columns('calendario_sanitario')}
    if 'dias_antecedencia_lista_espera' not in colunas:
        with op.batch_alter_table('calendario_sanitario') as batch:
            batch.add_column(sa.Column('dias_antecedencia_lista_espera', sa.Integer(), nullable=True))
    if insp.has_table(TABELA):
        return
    op.create_table(
        TABELA,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
        sa.Column('ultima_execucao_em', sa.DateTime(), nullable=True),
        sa.Column('ultima_execucao_origem', sa.String(), nullable=True),
        sa.Column('ultima_execucao_status', sa.String(), nullable=True),
        sa.Column('ultima_execucao_entraram', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ultima_execucao_regras', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ultima_execucao_regras_na_janela', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ultimo_erro', sa.String(), nullable=True),
        sa.Column('ultima_diaria_em', sa.Date(), nullable=True),
        sa.Column('ultimo_aviso_em', sa.Date(), nullable=True),
        sa.Column('em_execucao_ate', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('fazenda_id', name='uq_rotina_lista_espera_estado_fazenda'),
    )
    op.create_index(op.f('ix_rotina_lista_espera_estado_fazenda_id'), TABELA, ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA):
        op.drop_table(TABELA)
    colunas = {c['name'] for c in insp.get_columns('calendario_sanitario')}
    if 'dias_antecedencia_lista_espera' in colunas:
        with op.batch_alter_table('calendario_sanitario') as batch:
            batch.drop_column('dias_antecedencia_lista_espera')
