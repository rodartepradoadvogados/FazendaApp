"""parametro_fazenda: fazenda_id (Fase 0 — parâmetros deixam de ser globais)

`chave` era única no sistema inteiro: TODAS as fazendas dividiam o mesmo PEV,
a mesma gestação, as mesmas metas. Agora a chave real é (chave, fazenda_id):

  - fazenda_id NULL = padrão global (é o que o seed cria, e o que toda
    fazenda enxerga enquanto não personalizar nada);
  - uma linha com fazenda_id preenchido = personalização daquela fazenda,
    que tem prioridade na leitura (ver rules/parametros.py::_linha).

As linhas que já existem viram o padrão global (fazenda_id fica NULL), então
nada muda de valor para quem já usa o sistema.

Revision ID: d1e2f3a4b5c6
Revises: 0738880aaec2
Create Date: 2026-07-28 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = '0738880aaec2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('parametro_fazenda', sa.Column('fazenda_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_parametro_fazenda_fazenda_id'), 'parametro_fazenda', ['fazenda_id'], unique=False)

    # O unique de `chave` sozinho vira o par (chave, fazenda_id). No SQLite o
    # unique de Field(unique=True) é um ÍNDICE (ix_parametro_fazenda_chave),
    # não uma constraint nomeada — por isso troca índice por índice.
    op.drop_index('ix_parametro_fazenda_chave', table_name='parametro_fazenda')
    op.create_index('ix_parametro_fazenda_chave', 'parametro_fazenda', ['chave'], unique=False)
    op.create_index(
        'uq_parametro_fazenda_chave_fazenda', 'parametro_fazenda', ['chave', 'fazenda_id'], unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_parametro_fazenda_chave_fazenda', table_name='parametro_fazenda')
    op.drop_index('ix_parametro_fazenda_chave', table_name='parametro_fazenda')
    op.create_index('ix_parametro_fazenda_chave', 'parametro_fazenda', ['chave'], unique=True)
    op.drop_index(op.f('ix_parametro_fazenda_fazenda_id'), table_name='parametro_fazenda')
    op.drop_column('parametro_fazenda', 'fazenda_id')
