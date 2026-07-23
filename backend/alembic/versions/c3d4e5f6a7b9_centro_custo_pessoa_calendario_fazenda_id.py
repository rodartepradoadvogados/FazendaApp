"""centro_custo/pessoa/calendario_sanitario: fazenda_id (piloto conservador)

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-07-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    # centro_custo: coluna aditiva + troca do unique(nome) global por
    # unique(nome, fazenda_id) — dois tenants podem, cada um, ter seu
    # próprio "Pecuária Leiteira".
    op.add_column('centro_custo', sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_centro_custo_fazenda_id'), 'centro_custo', ['fazenda_id'], unique=False)
    if fazenda_1_existe:
        conn.execute(sa.text("UPDATE centro_custo SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
    with op.batch_alter_table('centro_custo', schema=None) as batch_op:
        # SQLite: o unique(nome) original foi criado via Field(unique=True),
        # que o SQLModel registra como um índice único simples — remove pelo
        # nome de índice autogerado antes de recriar como composto.
        try:
            batch_op.drop_index('ix_centro_custo_nome')
        except Exception:
            pass
        batch_op.create_index('ix_centro_custo_nome', ['nome'], unique=False)
        batch_op.create_unique_constraint('uq_centro_custo_nome_fazenda', ['nome', 'fazenda_id'])

    # pessoa: coluna aditiva — sem retroatividade em cima de nenhum outro
    # cadastro (ver Pessoa em fazenda/models/pessoal.py).
    op.add_column('pessoa', sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_pessoa_fazenda_id'), 'pessoa', ['fazenda_id'], unique=False)
    if fazenda_1_existe:
        conn.execute(sa.text("UPDATE pessoa SET fazenda_id = 1 WHERE fazenda_id IS NULL"))

    # calendario_sanitario: já é a regra real e editável (não um valor fixo
    # em Python) — só precisa de fazenda_id para nascer vazia numa fazenda
    # nova, mantendo o que já foi lançado na fazenda #1.
    op.add_column('calendario_sanitario', sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_calendario_sanitario_fazenda_id'), 'calendario_sanitario', ['fazenda_id'], unique=False)
    if fazenda_1_existe:
        conn.execute(sa.text("UPDATE calendario_sanitario SET fazenda_id = 1 WHERE fazenda_id IS NULL"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_calendario_sanitario_fazenda_id'), table_name='calendario_sanitario')
    op.drop_column('calendario_sanitario', 'fazenda_id')

    op.drop_index(op.f('ix_pessoa_fazenda_id'), table_name='pessoa')
    op.drop_column('pessoa', 'fazenda_id')

    with op.batch_alter_table('centro_custo', schema=None) as batch_op:
        batch_op.drop_constraint('uq_centro_custo_nome_fazenda', type_='unique')
        batch_op.drop_index('ix_centro_custo_nome')
        batch_op.create_index('ix_centro_custo_nome', ['nome'], unique=True)
    op.drop_index(op.f('ix_centro_custo_fazenda_id'), table_name='centro_custo')
    op.drop_column('centro_custo', 'fazenda_id')
