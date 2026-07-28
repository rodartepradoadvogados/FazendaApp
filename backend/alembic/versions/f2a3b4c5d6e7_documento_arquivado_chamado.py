"""documento_arquivado + chamado: arquivo fiscal-contábil (Supabase Storage) e chamados de suporte

Arquivo integral de notas fiscais, CCIR, IRPF/IRPJ, inscrição estadual,
matrículas, contratos de trabalho/prestação de serviço etc., com upload
perguntando "inserir no balanço?" — o conteúdo vai para o Supabase Storage,
aqui só ficam os metadados (ver fazenda/models/documentos.py,
fazenda/rules/supabase_storage.py e fazenda/api/routers/documentos.py).
Chamado é o suporte aberto pelo contador (ou fazenda) — escrita sujeita ao
mesmo bloqueio do contador, destravável por senha (ver
fazenda/auth.py::bloquear_escrita_contador).

Revision ID: f2a3b4c5d6e7
Revises: 81ad18d4e7a9
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = '81ad18d4e7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'documento_arquivado',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('categoria', sa.String(), nullable=False),
        sa.Column('nome_original', sa.String(), nullable=False),
        sa.Column('caminho_storage', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
        sa.Column('data_documento', sa.Date(), nullable=True),
        sa.Column('data_upload', sa.DateTime(), nullable=False),
        sa.Column('enviado_por', sa.Integer(), nullable=True),
        sa.Column('inserir_no_balanco', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('numero_lancamento', sa.String(), nullable=True),
        sa.Column('descricao', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['enviado_por'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_documento_arquivado_fazenda_id'), 'documento_arquivado', ['fazenda_id'])
    op.create_index(op.f('ix_documento_arquivado_categoria'), 'documento_arquivado', ['categoria'])

    op.create_table(
        'chamado',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('assunto', sa.String(), nullable=False),
        sa.Column('descricao', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='aberto'),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.Column('resposta', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chamado_fazenda_id'), 'chamado', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_chamado_fazenda_id'), table_name='chamado')
    op.drop_table('chamado')
    op.drop_index(op.f('ix_documento_arquivado_categoria'), table_name='documento_arquivado')
    op.drop_index(op.f('ix_documento_arquivado_fazenda_id'), table_name='documento_arquivado')
    op.drop_table('documento_arquivado')
