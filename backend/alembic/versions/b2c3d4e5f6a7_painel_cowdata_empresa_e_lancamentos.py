"""painel cowdata: fazenda.eh_empresa_cowdata + lancamento_cowdata

Painel Mestre CowData (aprovado pelo usuário): a CowData ganha uma linha
própria em `fazenda` (marcada `eh_empresa_cowdata`) para ancorar Pessoa/
FolhaPagamento da própria equipe (Equipe CowData, ver
fazenda/api/routers/painel_cowdata.py) sem nunca aparecer como fazenda-
cliente, e uma tabela nova e isolada para o livro-caixa interno da CowData
(Financeiro CowData — independente do Financeiro de qualquer fazenda).

Revision ID: b2c3d4e5f6a7
Revises: a3f9c1e2d4b6
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a3f9c1e2d4b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'fazenda',
        sa.Column('eh_empresa_cowdata', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        'lancamento_cowdata',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('categoria', sa.String(), nullable=False),
        sa.Column('descricao', sa.String(), nullable=False),
        sa.Column('contraparte', sa.String(), nullable=True),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('lancamento_cowdata')
    op.drop_column('fazenda', 'eh_empresa_cowdata')
