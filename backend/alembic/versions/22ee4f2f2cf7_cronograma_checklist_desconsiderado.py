"""cronograma_sanitario: checklist_desconsiderado

Fase 1, passo 8 do redesenho do evento sanitário
(docs/redesenho-evento-sanitario.md, seção 3.2.5 — "Desconsiderar
cronograma") — confirma a Ocorrência sem passar pelo checklist, decisão por
Ocorrência, nunca muda a Regra. Migração ADITIVA, SEM BACKFILL — todo
cronograma existente nasce com checklist_desconsiderado=False (nenhuma regra
de hoje muda de comportamento).

Revision ID: 22ee4f2f2cf7
Revises: b3c1e9d24f07
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22ee4f2f2cf7'
down_revision: Union[str, Sequence[str], None] = 'b3c1e9d24f07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('cronograma_sanitario', sa.Column(
        'checklist_desconsiderado', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.add_column('cronograma_sanitario', sa.Column('checklist_desconsiderado_motivo', sa.String(), nullable=True))
    op.add_column('cronograma_sanitario', sa.Column('checklist_desconsiderado_em', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cronograma_sanitario', 'checklist_desconsiderado_em')
    op.drop_column('cronograma_sanitario', 'checklist_desconsiderado_motivo')
    op.drop_column('cronograma_sanitario', 'checklist_desconsiderado')
