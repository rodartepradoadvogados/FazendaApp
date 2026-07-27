"""cofre de acesso: pedido/sessao/auditoria de suporte + fazenda.exige_aprovacao + usuario.nivel_sigilo_maximo

Cofre de acesso (aprovado pelo usuário, adaptado do painel de referência
Lúmen): formaliza e audita todo acesso de suporte da CowData aos dados de
uma fazenda-cliente — ver fazenda/api/routers/cofre_acesso.py e
fazenda/models/cofre_acesso.py.

Revision ID: d7e8f9a0b1c2
Revises: b2c3d4e5f6a7
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'fazenda',
        sa.Column('exige_aprovacao_suporte', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('usuario', sa.Column('nivel_sigilo_maximo', sa.String(), nullable=True))

    op.create_table(
        'pedido_acesso_suporte',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('aprovado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('pedido_em', sa.DateTime(), nullable=False),
        sa.Column('decidido_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['aprovado_por_usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pedido_acesso_suporte_fazenda_id'), 'pedido_acesso_suporte', ['fazenda_id'])
    op.create_index(op.f('ix_pedido_acesso_suporte_usuario_id'), 'pedido_acesso_suporte', ['usuario_id'])

    op.create_table(
        'sessao_acesso_suporte',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pedido_id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.String(), nullable=False),
        sa.Column('iniciada_em', sa.DateTime(), nullable=False),
        sa.Column('expira_em', sa.DateTime(), nullable=False),
        sa.Column('encerrada_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['pedido_id'], ['pedido_acesso_suporte.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sessao_acesso_suporte_pedido_id'), 'sessao_acesso_suporte', ['pedido_id'])
    op.create_index(op.f('ix_sessao_acesso_suporte_fazenda_id'), 'sessao_acesso_suporte', ['fazenda_id'])
    op.create_index(op.f('ix_sessao_acesso_suporte_usuario_id'), 'sessao_acesso_suporte', ['usuario_id'])

    op.create_table(
        'auditoria_acesso_suporte',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('acao', sa.String(), nullable=False),
        sa.Column('quando', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_auditoria_acesso_suporte_fazenda_id'), 'auditoria_acesso_suporte', ['fazenda_id'])
    op.create_index(op.f('ix_auditoria_acesso_suporte_usuario_id'), 'auditoria_acesso_suporte', ['usuario_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('auditoria_acesso_suporte')
    op.drop_table('sessao_acesso_suporte')
    op.drop_table('pedido_acesso_suporte')
    op.drop_column('usuario', 'nivel_sigilo_maximo')
    op.drop_column('fazenda', 'exige_aprovacao_suporte')
