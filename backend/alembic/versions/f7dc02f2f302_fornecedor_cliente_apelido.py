"""fornecedor_cliente_apelido: apelido aprendido nome bruto -> nome canônico

Quando a leitura automática de documento (XML/OCR) não bate com nada do
cadastro de Fornecedor, o usuário pode ensinar o sistema a reconhecer aquele
texto bruto da nota (ex.: "COOP.AGRO.PROD.R.S.GOIANO - COMIGO") como um nome
já cadastrado (ex.: "COMIGO") — por fazenda, nunca cruzando tenants.

Revision ID: f7dc02f2f302
Revises: 15c03392acbe
Create Date: 2026-08-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f7dc02f2f302'
down_revision: Union[str, Sequence[str], None] = '15c03392acbe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente (`insp.has_table`) — a subida da aplicação chama
    # `SQLModel.metadata.create_all` como rede de segurança ANTES desta
    # migração rodar em produção, o que já criaria a tabela (nova no model)
    # e faria `op.create_table` falhar com "table already exists".
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('fornecedor_cliente_apelido'):
        op.create_table(
            'fornecedor_cliente_apelido',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('nome_bruto', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('nome_canonico', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome_bruto', 'fazenda_id', name='uq_apelido_nome_bruto_fazenda'),
        )
        op.create_index(op.f('ix_fornecedor_cliente_apelido_fazenda_id'), 'fornecedor_cliente_apelido', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_fornecedor_cliente_apelido_nome_bruto'), 'fornecedor_cliente_apelido', ['nome_bruto'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fornecedor_cliente_apelido_nome_bruto'), table_name='fornecedor_cliente_apelido')
    op.drop_index(op.f('ix_fornecedor_cliente_apelido_fazenda_id'), table_name='fornecedor_cliente_apelido')
    op.drop_table('fornecedor_cliente_apelido')
