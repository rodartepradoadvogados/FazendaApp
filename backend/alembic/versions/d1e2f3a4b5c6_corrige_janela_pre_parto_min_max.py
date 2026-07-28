"""corrige valores seedados de pre_parto_min/pre_parto_max (janela errada)

Os parâmetros pre_parto_min/pre_parto_max foram seedados com os valores da
janela do período seco/Secagem (31/60 dias antes do parto) em vez dos
corretos para Pré-parto (0/30 dias antes do parto — janela que vem DEPOIS da
Secagem, não junto). Ver fazenda/rules/parametros.py e agenda_engine.py.

Só corrige quem ainda está no valor errado original — nunca sobrescreve um
valor que o usuário já tenha editado manualmente em Configurações > Parâmetros.

Revision ID: d1e2f3a4b5c6
Revises: 0738880aaec2
Create Date: 2026-07-28 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = '0738880aaec2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE parametro_fazenda SET valor = '0' WHERE chave = 'pre_parto_min' AND valor = '31'"
    ))
    conn.execute(sa.text(
        "UPDATE parametro_fazenda SET valor = '30' WHERE chave = 'pre_parto_max' AND valor = '60'"
    ))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE parametro_fazenda SET valor = '31' WHERE chave = 'pre_parto_min' AND valor = '0'"
    ))
    conn.execute(sa.text(
        "UPDATE parametro_fazenda SET valor = '60' WHERE chave = 'pre_parto_max' AND valor = '30'"
    ))
