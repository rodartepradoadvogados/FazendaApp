"""cronograma sanitario: origem/motivo do animal, hora e motivo de cancelamento do agendamento

Fatia 7 do planejamento unificado (docs/agents/auditoria-preventivo-agenda/
planejamento/06-planejamento-unificado.md, secao 7, R6/R9). Migracao ADITIVA,
sem backfill de significado:

  cronograma_sanitario_animal.origem  -- 'janela' (padrao: todo animal ja
      existente entrou pela regra) | 'fora_janela' (R6, incluido a mao);
  cronograma_sanitario_animal.motivo  -- por que entrou fora da janela ou por
      que foi desconsiderado da lista de espera (NULL nas linhas existentes);
  cronograma_sanitario.hora           -- hora do agendamento ('HH:MM', opcional);
  cronograma_sanitario.motivo_cancelamento -- motivo do cancelamento (R9).

O estagio 'em_montagem' (rascunho do assistente 'Criar agendamento') e so um
novo valor de texto em cronograma_sanitario.status: sem mudanca de schema.

Revision ID: a7c1e5d94b20
Revises: 3131ff8d4cd9
Create Date: 2026-09-29 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c1e5d94b20'
down_revision: Union[str, Sequence[str], None] = '3131ff8d4cd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('cronograma_sanitario_animal', sa.Column(
        'origem', sa.String(), nullable=False, server_default='janela',
    ))
    op.add_column('cronograma_sanitario_animal', sa.Column('motivo', sa.String(), nullable=True))
    op.add_column('cronograma_sanitario', sa.Column('hora', sa.String(), nullable=True))
    op.add_column('cronograma_sanitario', sa.Column('motivo_cancelamento', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cronograma_sanitario', 'motivo_cancelamento')
    op.drop_column('cronograma_sanitario', 'hora')
    op.drop_column('cronograma_sanitario_animal', 'motivo')
    op.drop_column('cronograma_sanitario_animal', 'origem')
