"""tipo_servico_reprodutivo/metodo_servico_reprodutivo: unique(nome) -> unique(nome, fazenda_id)

Revision ID: c1d2e3f4a5b6
Revises: b6c7d8e9f0a1
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b6c7d8e9f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    tipo_servico_reprodutivo e metodo_servico_reprodutivo já tinham a coluna
    fazenda_id (aditiva, nunca preenchida por nenhum router até agora), mas o
    `nome` continuava com unique(nome) GLOBAL — o mesmo problema já corrigido
    em centro_custo/principio_ativo/doenca: uma 2ª fazenda nunca conseguiria
    cadastrar "IATF" de novo. Troca para unique(nome, fazenda_id) e faz o
    backfill da fazenda #1 (piloto), mesmo padrão de c3d4e5f6a7b9.
    """
    conn = op.get_bind()
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()
    if fazenda_1_existe:
        conn.execute(sa.text(
            "UPDATE tipo_servico_reprodutivo SET fazenda_id = 1 WHERE fazenda_id IS NULL"
        ))
        conn.execute(sa.text(
            "UPDATE metodo_servico_reprodutivo SET fazenda_id = 1 WHERE fazenda_id IS NULL"
        ))

    with op.batch_alter_table('tipo_servico_reprodutivo', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_tipo_servico_reprodutivo_nome')
        except Exception:
            pass
        batch_op.create_index('ix_tipo_servico_reprodutivo_nome', ['nome'], unique=False)
        batch_op.create_unique_constraint(
            'uq_tipo_servico_reprodutivo_nome_fazenda', ['nome', 'fazenda_id']
        )

    with op.batch_alter_table('metodo_servico_reprodutivo', schema=None) as batch_op:
        try:
            batch_op.drop_index('ix_metodo_servico_reprodutivo_nome')
        except Exception:
            pass
        batch_op.create_index('ix_metodo_servico_reprodutivo_nome', ['nome'], unique=False)
        batch_op.create_unique_constraint(
            'uq_metodo_servico_reprodutivo_nome_fazenda', ['nome', 'fazenda_id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('metodo_servico_reprodutivo', schema=None) as batch_op:
        batch_op.drop_constraint('uq_metodo_servico_reprodutivo_nome_fazenda', type_='unique')
        batch_op.drop_index('ix_metodo_servico_reprodutivo_nome')
        batch_op.create_index('ix_metodo_servico_reprodutivo_nome', ['nome'], unique=True)

    with op.batch_alter_table('tipo_servico_reprodutivo', schema=None) as batch_op:
        batch_op.drop_constraint('uq_tipo_servico_reprodutivo_nome_fazenda', type_='unique')
        batch_op.drop_index('ix_tipo_servico_reprodutivo_nome')
        batch_op.create_index('ix_tipo_servico_reprodutivo_nome', ['nome'], unique=True)
