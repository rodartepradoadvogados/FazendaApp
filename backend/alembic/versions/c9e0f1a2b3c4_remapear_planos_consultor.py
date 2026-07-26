"""remapear planos do consultor: basico/intermediario/avancado -> standard/gold/diamond

Revision ID: c9e0f1a2b3c4
Revises: c7d8e9f0a1b2
Create Date: 2026-07-25 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e0f1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (plano_antigo, plano_novo, limite_fazendas_novo) — preço não é coluna do
# contrato (só do catálogo, lido ao vivo), então só plano/limite precisam
# remapear aqui. Decisão jul/2026: sem tier Silver para consultor; Diamond
# sobe de 15 para 20 fazendas.
REMAPEAMENTO = [
    ('consultor_basico', 'consultor_standard', 3),
    ('consultor_intermediario', 'consultor_gold', 8),
    ('consultor_avancado', 'consultor_diamond', 20),
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    for antigo, novo, limite in REMAPEAMENTO:
        conn.execute(
            sa.text("UPDATE contrato_consultor SET plano = :novo, limite_fazendas = :limite WHERE plano = :antigo"),
            {"novo": novo, "limite": limite, "antigo": antigo},
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    for antigo, novo, limite_antigo in [('consultor_basico', 'consultor_standard', 3),
                                          ('consultor_intermediario', 'consultor_gold', 8),
                                          ('consultor_avancado', 'consultor_diamond', 15)]:
        conn.execute(
            sa.text("UPDATE contrato_consultor SET plano = :antigo, limite_fazendas = :limite WHERE plano = :novo"),
            {"antigo": antigo, "limite": limite_antigo, "novo": novo},
        )
