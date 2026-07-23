"""conta_corrente: fazenda_id (piloto conservador de multi-fazenda)

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Coluna aditiva e nula por padrão — sem FK real no banco (mesma
    # convenção já usada em animal.fazenda_id, ver f1a2b3c4d5e6). Backfill:
    # toda conta corrente já cadastrada (as 2 reais da fazenda #1) recebe
    # fazenda_id=1, para continuar aparecendo exatamente como antes na
    # listagem já filtrada por fazenda_id.
    op.add_column('conta_corrente', sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_conta_corrente_fazenda_id'), 'conta_corrente', ['fazenda_id'], unique=False)
    conn = op.get_bind()
    ja_existe_fazenda_1 = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()
    if ja_existe_fazenda_1:
        conn.execute(sa.text("UPDATE conta_corrente SET fazenda_id = 1 WHERE fazenda_id IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_conta_corrente_fazenda_id'), table_name='conta_corrente')
    op.drop_column('conta_corrente', 'fazenda_id')
