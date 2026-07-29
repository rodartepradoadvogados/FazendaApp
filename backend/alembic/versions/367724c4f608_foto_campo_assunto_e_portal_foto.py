"""foto_campo_assunto_e_portal_foto: assunto opcional da foto do campo
(animal/lote/outro) e vínculo de PortalMensagem com a foto correspondente

Fotos do campo passam a morar dentro do Portal (tipo="foto" em
PortalMensagem), com o assunto opcional marcado na captura. Ver
fazenda/api/routers/fotos.py e fazenda/models/sistema.py::PortalMensagem.

Revision ID: 367724c4f608
Revises: 06f55bae449e
Create Date: 2026-07-29 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '367724c4f608'
down_revision: Union[str, Sequence[str], None] = '06f55bae449e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('foto_campo', sa.Column('tipo_assunto', sa.String(), nullable=True))
    op.add_column('foto_campo', sa.Column('animal_id', sa.Integer(), nullable=True))
    op.add_column('foto_campo', sa.Column('lotes', sa.String(), nullable=True))
    op.add_column('foto_campo', sa.Column('assunto_fixo', sa.String(), nullable=True))
    op.create_index(op.f('ix_foto_campo_animal_id'), 'foto_campo', ['animal_id'])
    op.add_column('portal_mensagem', sa.Column('foto_campo_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('portal_mensagem', 'foto_campo_id')
    op.drop_index(op.f('ix_foto_campo_animal_id'), table_name='foto_campo')
    op.drop_column('foto_campo', 'assunto_fixo')
    op.drop_column('foto_campo', 'lotes')
    op.drop_column('foto_campo', 'animal_id')
    op.drop_column('foto_campo', 'tipo_assunto')
