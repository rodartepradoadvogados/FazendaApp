"""classificacao_lancamento: classificação cadastrável de conta a pagar/receber

Campo "classificação" (ex.: Medicamentos, Ração, Manutenção) selecionável ao
lançar uma conta a pagar, cadastrável na hora — mesmo padrão de
TipoDocumento/FormaPagamentoCadastro (Configurações > Parâmetros
financeiros). `conta_gerencial.classificacao` guarda o nome escolhido (texto
livre validado contra o cadastro, igual a tipo_documento/centro_custo).

Revision ID: c8e91a4f6b23
Revises: f7dc02f2f302
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c8e91a4f6b23'
down_revision: Union[str, Sequence[str], None] = 'f7dc02f2f302'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente — `SQLModel.metadata.create_all` roda como rede de
    # segurança antes desta migração em produção (ver f7dc02f2f302).
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('classificacao_lancamento'):
        op.create_table(
            'classificacao_lancamento',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('nome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nome', 'fazenda_id', name='uq_classificacao_lancamento_nome_fazenda'),
        )
        op.create_index(op.f('ix_classificacao_lancamento_fazenda_id'), 'classificacao_lancamento', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_classificacao_lancamento_nome'), 'classificacao_lancamento', ['nome'], unique=False)

    colunas_conta_gerencial = {c["name"] for c in insp.get_columns('conta_gerencial')}
    if 'classificacao' not in colunas_conta_gerencial:
        op.add_column('conta_gerencial', sa.Column('classificacao', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('conta_gerencial', 'classificacao')
    op.drop_index(op.f('ix_classificacao_lancamento_nome'), table_name='classificacao_lancamento')
    op.drop_index(op.f('ix_classificacao_lancamento_fazenda_id'), table_name='classificacao_lancamento')
    op.drop_table('classificacao_lancamento')
