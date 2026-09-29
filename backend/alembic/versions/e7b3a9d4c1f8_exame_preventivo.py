"""exame preventivo no aplicar unico: inoculacao/leitura, resultado por animal, reagente e reteste

Fatia 9b do planejamento unificado (docs/agents/auditoria-preventivo-agenda/
planejamento/06-planejamento-unificado.md, secao 7; decisoes clinicas em
08-correcoes-fluxo-R5.md e 09-correcoes-R6.md). Migracao ADITIVA (so colunas
novas, todas anulaveis ou com padrao), sem backfill:

  cronograma_sanitario_aplicacao
      fase, inoculacao_aplicacao_id, tipo_teste, laudo, leitura_prevista_em,
      leitura_limite_em, data_evento_antes, hora_antes, leitura_horas,
      leitura_fora_janela, leitura_justificativa
  cronograma_sanitario_aplicacao_animal
      exame_resultado, espessura_mm, reteste_em, exame_resultado_id,
      notificado_em, notificado_por_usuario_id, notificado_por_nome,
      notificacao_ref
  cronograma_sanitario_animal
      reteste, data_devida, motivo_entrada

Idempotente por coluna (um banco montado por SQLModel.metadata.create_all ja
pode te-las — mesmo padrao das migracoes anteriores da serie).

Revision ID: e7b3a9d4c1f8
Revises: d5a7c3e91f26
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b3a9d4c1f8'
down_revision: Union[str, Sequence[str], None] = 'd5a7c3e91f26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APLICACAO = 'cronograma_sanitario_aplicacao'
ANIMAL_APL = 'cronograma_sanitario_aplicacao_animal'
ANIMAL_CRON = 'cronograma_sanitario_animal'

COLUNAS = [
    (APLICACAO, lambda: sa.Column('fase', sa.String(), nullable=True)),
    (APLICACAO, lambda: sa.Column('inoculacao_aplicacao_id', sa.Integer(), nullable=True)),
    (APLICACAO, lambda: sa.Column('tipo_teste', sa.String(), nullable=True)),
    (APLICACAO, lambda: sa.Column('laudo', sa.String(), nullable=True)),
    (APLICACAO, lambda: sa.Column('leitura_prevista_em', sa.DateTime(), nullable=True)),
    (APLICACAO, lambda: sa.Column('leitura_limite_em', sa.DateTime(), nullable=True)),
    (APLICACAO, lambda: sa.Column('data_evento_antes', sa.Date(), nullable=True)),
    (APLICACAO, lambda: sa.Column('hora_antes', sa.String(), nullable=True)),
    (APLICACAO, lambda: sa.Column('leitura_horas', sa.Float(), nullable=True)),
    (APLICACAO, lambda: sa.Column('leitura_fora_janela', sa.Boolean(), nullable=False, server_default=sa.false())),
    (APLICACAO, lambda: sa.Column('leitura_justificativa', sa.String(), nullable=True)),
    (ANIMAL_APL, lambda: sa.Column('exame_resultado', sa.String(), nullable=True)),
    (ANIMAL_APL, lambda: sa.Column('espessura_mm', sa.Float(), nullable=True)),
    (ANIMAL_APL, lambda: sa.Column('reteste_em', sa.Date(), nullable=True)),
    (ANIMAL_APL, lambda: sa.Column('exame_resultado_id', sa.Integer(), nullable=True)),
    (ANIMAL_APL, lambda: sa.Column('notificado_em', sa.DateTime(), nullable=True)),
    (ANIMAL_APL, lambda: sa.Column('notificado_por_usuario_id', sa.Integer(), nullable=True)),
    (ANIMAL_APL, lambda: sa.Column('notificado_por_nome', sa.String(), nullable=True)),
    (ANIMAL_APL, lambda: sa.Column('notificacao_ref', sa.String(), nullable=True)),
    (ANIMAL_CRON, lambda: sa.Column('reteste', sa.Boolean(), nullable=False, server_default=sa.false())),
    (ANIMAL_CRON, lambda: sa.Column('data_devida', sa.Date(), nullable=True)),
    (ANIMAL_CRON, lambda: sa.Column('motivo_entrada', sa.String(), nullable=True)),
]

INDICES = [
    (APLICACAO, 'fase'),
    (APLICACAO, 'inoculacao_aplicacao_id'),
    (ANIMAL_APL, 'exame_resultado'),
]


def _colunas(insp, tabela: str) -> set[str]:
    return {c['name'] for c in insp.get_columns(tabela)}


def upgrade() -> None:
    """Upgrade schema. Idempotente por coluna e por indice."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {t: _colunas(insp, t) for t in (APLICACAO, ANIMAL_APL, ANIMAL_CRON)}
    for tabela, fabrica in COLUNAS:
        col = fabrica()
        if col.name not in existentes[tabela]:
            op.add_column(tabela, col)
    insp = sa.inspect(bind)
    for tabela, coluna in INDICES:
        nome = op.f(f'ix_{tabela}_{coluna}')
        if nome not in {i['name'] for i in insp.get_indexes(tabela)}:
            op.create_index(nome, tabela, [coluna])


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for tabela, coluna in INDICES:
        nome = op.f(f'ix_{tabela}_{coluna}')
        if nome in {i['name'] for i in insp.get_indexes(tabela)}:
            op.drop_index(nome, table_name=tabela)
    insp = sa.inspect(bind)
    existentes = {t: _colunas(insp, t) for t in (APLICACAO, ANIMAL_APL, ANIMAL_CRON)}
    for tabela, fabrica in reversed(COLUNAS):
        nome = fabrica().name
        if nome in existentes[tabela]:
            with op.batch_alter_table(tabela) as lote:
                lote.drop_column(nome)
