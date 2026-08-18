"""pessoa_anexo: documentos (RG/CPF/contratos/holerite/comprovantes) anexados a uma Pessoa

Nova tabela `pessoa_anexo` — mesmo padrão de `pedido_anexo` (conteúdo no
Supabase Storage, só metadados aqui), com `categoria` restrita à lista fixa
CATEGORIAS_PESSOA_ANEXO e `data_validade` própria: é dela que a Agenda tira
o alerta de vencimento de "Contrato de trabalho por prazo determinado" (ver
fazenda/rules/agenda_engine.py).

Revision ID: 77c6d0d3e55c
Revises: 6aec9b930e1a
Create Date: 2026-08-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '77c6d0d3e55c'
down_revision: Union[str, Sequence[str], None] = '6aec9b930e1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('pessoa_anexo'):
        op.create_table(
            'pessoa_anexo',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('pessoa_id', sa.Integer(), nullable=False),
            sa.Column('nome_arquivo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('mime_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
            sa.Column('categoria', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('data_validade', sa.Date(), nullable=True),
            sa.Column('caminho_storage', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['pessoa_id'], ['pessoa.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_pessoa_anexo_fazenda_id'), 'pessoa_anexo', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_pessoa_anexo_pessoa_id'), 'pessoa_anexo', ['pessoa_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pessoa_anexo_pessoa_id'), table_name='pessoa_anexo')
    op.drop_index(op.f('ix_pessoa_anexo_fazenda_id'), table_name='pessoa_anexo')
    op.drop_table('pessoa_anexo')
