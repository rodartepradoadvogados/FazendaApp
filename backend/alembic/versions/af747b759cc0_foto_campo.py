"""foto_campo: fotos do campo capturadas no app móvel (Supabase Storage)

Bucket separado do arquivo fiscal-contábil (settings.supabase_bucket_fotos),
aqui só ficam os metadados — ver fazenda/models/fotos.py,
fazenda/rules/supabase_storage.py e fazenda/api/routers/fotos.py.

Revision ID: af747b759cc0
Revises: e5f6a7b8c9d0
Create Date: 2026-07-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af747b759cc0'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'foto_campo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('caminho_storage', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
        sa.Column('descricao', sa.String(), nullable=True),
        sa.Column('identificacao_animal', sa.String(), nullable=True),
        sa.Column('data_captura', sa.DateTime(), nullable=False),
        sa.Column('enviado_por', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['enviado_por'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_foto_campo_fazenda_id'), 'foto_campo', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_foto_campo_fazenda_id'), table_name='foto_campo')
    op.drop_table('foto_campo')
