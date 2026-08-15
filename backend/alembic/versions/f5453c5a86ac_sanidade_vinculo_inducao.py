"""sanidade: vínculo relacional com o lançamento de indução de lactação

Adiciona `sanidade.protocolo_inducao_lancamento_id` (FK para
protocolo_inducao_lancamento.id) — espelha `protocolo_iatf_lancamento_id`,
já existente, mas para a indução de lactação. Antes desse campo o vínculo
só existia como texto livre em `Sanidade.obs`
("Indução de lactação — D{dia}"), sem junção relacional possível.

Revision ID: f5453c5a86ac
Revises: 57c4539ee240
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5453c5a86ac'
down_revision: Union[str, Sequence[str], None] = '57c4539ee240'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sanidade', sa.Column('protocolo_inducao_lancamento_id', sa.Integer(), nullable=True))
    op.create_index(
        op.f('ix_sanidade_protocolo_inducao_lancamento_id'), 'sanidade', ['protocolo_inducao_lancamento_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sanidade_protocolo_inducao_lancamento_id'), table_name='sanidade')
    op.drop_column('sanidade', 'protocolo_inducao_lancamento_id')
