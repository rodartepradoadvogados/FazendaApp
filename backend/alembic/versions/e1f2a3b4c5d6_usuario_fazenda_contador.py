"""usuario_fazenda.contador: vinculo de contador externo (Painel do Contador)

Terceiro papel de UsuarioFazenda, ao lado de contratante/consultor — acesso
restrito a Financeiro em modo leitura/exportação, com casca visual própria
(ver fazenda/models/multitenant.py::UsuarioFazenda e
fazenda/api/routers/fazendas.py::vincular_usuario).

Revision ID: e1f2a3b4c5d6
Revises: d7e8f9a0b1c2
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'usuario_fazenda',
        sa.Column('contador', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('usuario_fazenda', 'contador')
