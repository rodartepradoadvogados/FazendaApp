"""cofre de acesso: assunto/observação do chamado + auditoria de ações da sessão

Suporta o fluxo de 3 janelas (fazenda → plano/módulos → motivo/assunto/
observação) do Painel CowData > Suporte > Acesso CowData, e a auditoria
granular de cada escrita feita durante uma sessão de suporte (ver
fazenda/models/cofre_acesso.py e main.py::_bloquear_modo_suporte).

Revision ID: e5e27b3f22aa
Revises: e92e4d3dedaa
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5e27b3f22aa'
down_revision: Union[str, Sequence[str], None] = 'e92e4d3dedaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('pedido_acesso_suporte', sa.Column('assunto_chamado', sa.String(), nullable=True))
    op.add_column('pedido_acesso_suporte', sa.Column('observacao', sa.String(), nullable=True))

    op.create_table(
        'acao_auditoria_suporte',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sessao_id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('metodo', sa.String(), nullable=False),
        sa.Column('caminho', sa.String(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('bloqueado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('quando', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessao_acesso_suporte.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_acao_auditoria_suporte_sessao_id'), 'acao_auditoria_suporte', ['sessao_id'])
    op.create_index(op.f('ix_acao_auditoria_suporte_fazenda_id'), 'acao_auditoria_suporte', ['fazenda_id'])
    op.create_index(op.f('ix_acao_auditoria_suporte_usuario_id'), 'acao_auditoria_suporte', ['usuario_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('acao_auditoria_suporte')
    op.drop_column('pedido_acesso_suporte', 'observacao')
    op.drop_column('pedido_acesso_suporte', 'assunto_chamado')
