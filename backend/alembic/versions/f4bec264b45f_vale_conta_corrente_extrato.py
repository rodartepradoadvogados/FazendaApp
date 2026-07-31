"""vale_funcionario/vale_avulso: conta_corrente_id + numero_lancamento_gerado

Vale de funcionário (e o análogo Vale avulso de Empreitada/Contrato/Diária)
sempre foi um adiantamento pago à parte — em dinheiro/pix/transferência — mas
nunca precisou estar ligado a uma conta bancária da fazenda, e nunca gerava
lançamento nenhum em Financeiro: o dinheiro saía do caixa/banco na hora e não
aparecia em lugar nenhum do extrato (`GET /lancamentos`, filtrado por
`ContaGerencial.conta_bancaria`). Isso corrige o furo: todo vale novo (que não
seja "desconto_integral_folha"/"desconto_proximo_pagamento" — esses não
movimentam banco nenhum na hora) passa a exigir uma conta corrente e gera seu
próprio ContaGerencial, já pago, com `conta_bancaria` preenchido a partir dela
(ver `criar_vale`/`criar_vale_avulso` em fazenda/api/routers/cadastro/).

- `conta_corrente_id`: vínculo RELACIONAL (FK), não string — sobrevive a
  editar/renomear a conta depois. Nullable para não quebrar vales já
  lançados antes desta coluna existir (não têm de onde inferir a conta).
- `numero_lancamento_gerado`: mesmo padrão de `FolhaPagamento`/`DiariaPagamento`
  — aponta para o ContaGerencial gerado, para permitir sincronizar/remover ao
  editar/excluir o vale.

Revision ID: f4bec264b45f
Revises: b20df48b733a
Create Date: 2026-07-31 08:56:50.415478

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4bec264b45f'
down_revision: Union[str, Sequence[str], None] = 'b20df48b733a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('vale_funcionario', sa.Column('conta_corrente_id', sa.Integer(), nullable=True))
    op.add_column('vale_funcionario', sa.Column('numero_lancamento_gerado', sa.String(), nullable=True))
    with op.batch_alter_table('vale_funcionario') as batch_op:
        batch_op.create_foreign_key(
            'fk_vale_funcionario_conta_corrente_id', 'conta_corrente', ['conta_corrente_id'], ['id'],
        )

    op.add_column('vale_avulso', sa.Column('conta_corrente_id', sa.Integer(), nullable=True))
    op.add_column('vale_avulso', sa.Column('numero_lancamento_gerado', sa.String(), nullable=True))
    with op.batch_alter_table('vale_avulso') as batch_op:
        batch_op.create_foreign_key(
            'fk_vale_avulso_conta_corrente_id', 'conta_corrente', ['conta_corrente_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('vale_avulso') as batch_op:
        batch_op.drop_constraint('fk_vale_avulso_conta_corrente_id', type_='foreignkey')
    op.drop_column('vale_avulso', 'numero_lancamento_gerado')
    op.drop_column('vale_avulso', 'conta_corrente_id')

    with op.batch_alter_table('vale_funcionario') as batch_op:
        batch_op.drop_constraint('fk_vale_funcionario_conta_corrente_id', type_='foreignkey')
    op.drop_column('vale_funcionario', 'numero_lancamento_gerado')
    op.drop_column('vale_funcionario', 'conta_corrente_id')
