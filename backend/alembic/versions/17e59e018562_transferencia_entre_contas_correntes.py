"""transferencia entre contas correntes

Cria só a tabela `transferencia_contas` (Transferência entre contas
correntes — Configurações > Parâmetros financeiros > Conta corrente >
"Transferir entre contas"). O autogenerate original detectou dezenas de
outras diferenças (FKs/índices) entre a cadeia de migrações e o schema real
do Neon — drift pré-existente, nada a ver com esta mudança — removidas daqui
a mão para o revision ficar só com o que esta feature precisa.

Idempotente (`insp.has_table`), mesmo padrão de 4ede0ee68b09 — precisa ser
seguro em qualquer ambiente onde a tabela já tenha nascido via
`SQLModel.metadata.create_all` (rede de segurança de
`database.py::create_db_and_tables`) antes desta migração rodar.

Revision ID: 17e59e018562
Revises: c1a2b3d4e5f6
Create Date: 2026-08-23 10:58:20.364854

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '17e59e018562'
down_revision: Union[str, Sequence[str], None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('transferencia_contas'):
        op.create_table(
            'transferencia_contas',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('conta_origem_id', sa.Integer(), nullable=False),
            sa.Column('conta_destino_id', sa.Integer(), nullable=False),
            sa.Column('valor', sa.Float(), nullable=False),
            sa.Column('data', sa.Date(), nullable=False),
            sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['conta_destino_id'], ['conta_corrente.id'], ),
            sa.ForeignKeyConstraint(['conta_origem_id'], ['conta_corrente.id'], ),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_transferencia_contas_conta_destino_id'), 'transferencia_contas', ['conta_destino_id'], unique=False)
        op.create_index(op.f('ix_transferencia_contas_conta_origem_id'), 'transferencia_contas', ['conta_origem_id'], unique=False)
        op.create_index(op.f('ix_transferencia_contas_fazenda_id'), 'transferencia_contas', ['fazenda_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if insp.has_table('transferencia_contas'):
        op.drop_index(op.f('ix_transferencia_contas_fazenda_id'), table_name='transferencia_contas')
        op.drop_index(op.f('ix_transferencia_contas_conta_origem_id'), table_name='transferencia_contas')
        op.drop_index(op.f('ix_transferencia_contas_conta_destino_id'), table_name='transferencia_contas')
        op.drop_table('transferencia_contas')
