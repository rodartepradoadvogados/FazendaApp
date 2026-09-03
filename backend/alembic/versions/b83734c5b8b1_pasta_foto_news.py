"""banco de fotos do milknews (pasta_foto_news, foto_news)

Idempotente por tabela (`insp.has_table`, mesmo padrão de 4ede0ee68b09) —
`fazenda/database.py::create_db_and_tables` roda `SQLModel.metadata.create_all`
como rede de segurança depois do `alembic upgrade head`, e testes (ver
test_migracao_tabelas_faltantes.py) simulam esse `create_all` batendo antes
desta migração, então `op.create_table` precisa tolerar a tabela já existir.

Revision ID: b83734c5b8b1
Revises: d3f8a1c96e02
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b83734c5b8b1'
down_revision: Union[str, Sequence[str], None] = 'd3f8a1c96e02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('pasta_foto_news'):
        op.create_table(
            'pasta_foto_news',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('criado_por', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['criado_por'], ['usuario.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if not insp.has_table('foto_news'):
        op.create_table(
            'foto_news',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('pasta_id', sa.Integer(), nullable=True),
            sa.Column('nome_arquivo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('caminho_storage', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('mime_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
            sa.Column('tags', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('enviado_por', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['pasta_id'], ['pasta_foto_news.id']),
            sa.ForeignKeyConstraint(['enviado_por'], ['usuario.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_foto_news_pasta_id'), 'foto_news', ['pasta_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_foto_news_pasta_id'), table_name='foto_news')
    op.drop_table('foto_news')
    op.drop_table('pasta_foto_news')
