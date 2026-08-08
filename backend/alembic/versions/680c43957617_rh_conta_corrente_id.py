"""folha/ferias/decimo_terceiro/rescisao/diaria_pagamento: conta_corrente_id

Stakeholder confirmado: "a rescisão e outros lançamentos não estão puxando
para eu lançar a conta que usei, o que faz dar problema de relatórios
gerenciais". `ContaGerencial.conta_bancaria` (texto livre) é o campo que os
relatórios gerenciais de fato filtram/agrupam — e, antes desta migração, só
o fluxo de Vale de funcionário (ver f4bec264b45f) o preenchia. Os outros 5
lançamentos de RH que geram ContaGerencial (Folha, Férias, 13º, Rescisão,
Diária) nunca perguntavam a conta bancária.

Replica o padrão já usado por `vale_funcionario`/`vale_avulso`: cada tabela
ganha `conta_corrente_id` — vínculo RELACIONAL (FK), não string, para
sobreviver a editar/renomear a conta depois — nullable e OPCIONAL (ao
contrário do vale, aqui a conta NUNCA é obrigatória: estes fluxos não têm o
conceito de forma_pagamento "dinheiro agora" do vale). O backend
(`_resolver_conta_corrente` em rh_folha.py) usa esse id para preencher
`ContaGerencial.conta_bancaria` a cada lançamento, e a própria coluna
existe para permitir a um formulário de edição pré-selecionar a conta já
escolhida — mesmo motivo de `ValeFuncionario.conta_corrente_id`.

Revision ID: 680c43957617
Revises: 0f3adf074568
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '680c43957617'
down_revision: Union[str, Sequence[str], None] = '0f3adf074568'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELAS = ["folha_pagamento", "ferias_funcionario", "decimo_terceiro", "rescisao_funcionario", "diaria_pagamento"]


def upgrade() -> None:
    """Upgrade schema."""
    for tabela in _TABELAS:
        op.add_column(tabela, sa.Column('conta_corrente_id', sa.Integer(), nullable=True))
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.create_foreign_key(
                f'fk_{tabela}_conta_corrente_id', 'conta_corrente', ['conta_corrente_id'], ['id'],
            )


def downgrade() -> None:
    """Downgrade schema."""
    for tabela in reversed(_TABELAS):
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.drop_constraint(f'fk_{tabela}_conta_corrente_id', type_='foreignkey')
        op.drop_column(tabela, 'conta_corrente_id')
