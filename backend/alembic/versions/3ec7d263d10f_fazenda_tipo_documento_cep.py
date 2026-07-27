"""fazenda: tipo_documento (cpf/cnpj) e cep

Colunas aditivas na tabela fazenda — tipo_documento define qual máscara vale
pra `documento` (o cadastro pergunta CPF ou CNPJ, não deixa campo livre, ver
FazendasAdmin.tsx). `cep` complementa o endereço já existente.

Revision ID: 3ec7d263d10f
Revises: 80dc9565ce9f
Create Date: 2026-07-27 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ec7d263d10f'
down_revision: Union[str, Sequence[str], None] = '80dc9565ce9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fazenda', sa.Column('tipo_documento', sa.String(), nullable=True))
    op.add_column('fazenda', sa.Column('cep', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('fazenda', 'cep')
    op.drop_column('fazenda', 'tipo_documento')
