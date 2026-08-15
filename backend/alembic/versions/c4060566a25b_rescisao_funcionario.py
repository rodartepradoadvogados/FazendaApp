"""rescisao_funcionario: tabela de acompanhamento (simulacao -> fechada)

Fase 1/2/4/5 do plano de persistir/editar/rastrear a Rescisão contratual
(CLT), até aqui só um cálculo que gerava direto uma ContaGerencial sem
tabela própria (mesmo padrão hoje usado por Férias/13º salário). A rescisão
nasce `simulacao` (livre para editar/recalcular, sem nada em Financeiro) e só
vira lançamento real ao fechar (`status="fechada"`, gera 1 ou N
ContaGerencial conforme `forma_lancamento`) — ver
fazenda/models/pessoal.py::RescisaoFuncionario e
fazenda/api/routers/cadastro/rh_folha.py.

Revision ID: c4060566a25b
Revises: 20dc777765f9
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4060566a25b'
down_revision: Union[str, Sequence[str], None] = '20dc777765f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rescisao_funcionario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pessoa_id', sa.Integer(), nullable=False),
        sa.Column('tipo_rescisao', sa.String(), nullable=False),
        sa.Column('data_desligamento', sa.Date(), nullable=False),
        sa.Column('dias_ferias_vencidas', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('aviso_previo_trabalhado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('salario_base', sa.Float(), nullable=False),
        sa.Column('data_admissao', sa.Date(), nullable=False),
        sa.Column('valor_saldo_salario', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_aviso_previo', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_ferias_vencidas', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_ferias_proporcionais', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_decimo_terceiro_proporcional', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_multa_fgts', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_inss', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_ir', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_vale_em_aberto', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_bruto', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('valor_total', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('dias_saldo_salario', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('dias_aviso_previo', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('dias_aviso_previo_indenizados', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('meses_ferias_proporcionais', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('meses_decimo_terceiro', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('percentual_multa_fgts', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('status', sa.String(), nullable=False, server_default=sa.text("'simulacao'")),
        sa.Column('forma_lancamento', sa.String(), nullable=True),
        sa.Column('data_fechamento', sa.Date(), nullable=True),
        sa.Column('data_pagamento', sa.Date(), nullable=True),
        sa.Column('inativou_pessoa', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('numero_lancamento_gerado', sa.String(), nullable=True),
        sa.Column('centro_custo', sa.String(), nullable=False, server_default=sa.text("'Pecuária Leiteira'")),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('fazenda_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['pessoa_id'], ['pessoa.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_rescisao_funcionario_fazenda_id'), 'rescisao_funcionario', ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('rescisao_funcionario')
