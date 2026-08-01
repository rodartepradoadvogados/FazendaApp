"""lancamento recorrente

Modelo de conta recorrente (energia, internet, telefone, assinatura, aluguel)
com os dados FIXOS cadastrados uma vez — ver fazenda/models/financeiro.py::
LancamentoRecorrente e fazenda/api/routers/financeiro.py (seção "Lançamentos
recorrentes"). Gerar a partir do modelo cria um ContaGerencial/LancamentoItem
comum (mesma tabela de sempre), esta migração só cria a tabela do MODELO.

Revision ID: e4e1748b2258
Revises: b297e9dc71d7
Create Date: 2026-08-01 00:43:36.176547

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e4e1748b2258'
down_revision: Union[str, Sequence[str], None] = 'b297e9dc71d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'lancamento_recorrente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.Column('descricao', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tipo', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('fornecedor_cliente', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('centro_custo', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('codigo_conta_gerencial', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('nome_conta_gerencial', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('tipo_item', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('responsavel_padrao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('tipo_documento_padrao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('forma_pagamento_padrao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('conta_bancaria_padrao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('dia_vencimento', sa.Integer(), nullable=True),
        sa.Column('periodicidade', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('observacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('ultimo_numero_lancamento', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('ultima_geracao_em', sa.Date(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lancamento_recorrente_fazenda_id'), 'lancamento_recorrente', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lancamento_recorrente_fazenda_id'), table_name='lancamento_recorrente')
    op.drop_table('lancamento_recorrente')
