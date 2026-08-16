"""pedido_anexo: documentos (orçamento/OS/outro) anexados a um Pedido

Nova tabela `pedido_anexo` — mesmo padrão de `lancamento_anexo` (conteúdo no
Supabase Storage, só metadados aqui), com `categoria` restrita a
"Orçamento"/"Ordem de serviço"/"Outro documento" e `data_validade` própria:
é dela que a Agenda tira o alerta de vencimento (2 dias antes) enquanto o
pedido segue "aberto" ou "parcialmente_atendido" (ver PUT /pedidos/{id}/anexos
e fazenda/rules/agenda_engine.py).

Revision ID: 6cfa00787699
Revises: 17c21279ba26
Create Date: 2026-08-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '6cfa00787699'
down_revision: Union[str, Sequence[str], None] = '17c21279ba26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente (`insp.has_table`) — mesmo motivo de 4ede0ee68b09: a subida
    # da aplicação chama `SQLModel.metadata.create_all` como rede de
    # segurança ANTES desta migração rodar em produção, o que já criaria
    # `pedido_anexo` (tabela nova do model) e faria `op.create_table` falhar
    # com "table already exists".
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('pedido_anexo'):
        op.create_table(
            'pedido_anexo',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('pedido_id', sa.Integer(), nullable=False),
            sa.Column('nome_arquivo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('mime_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('tamanho_bytes', sa.Integer(), nullable=False),
            sa.Column('categoria', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('data_validade', sa.Date(), nullable=True),
            sa.Column('caminho_storage', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['pedido_id'], ['pedido.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_pedido_anexo_fazenda_id'), 'pedido_anexo', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_pedido_anexo_pedido_id'), 'pedido_anexo', ['pedido_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pedido_anexo_pedido_id'), table_name='pedido_anexo')
    op.drop_index(op.f('ix_pedido_anexo_fazenda_id'), table_name='pedido_anexo')
    op.drop_table('pedido_anexo')
