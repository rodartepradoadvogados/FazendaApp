"""medicamento_comercial: classificacao_medicamento

Pedido do usuário (01/09/2026): o cadastro central de medicamento do Painel
CowData tinha um campo "Categoria/indicações" que na verdade é só indicação
(doença tratada) — a "categoria" de verdade (antimicrobiano, anti-inflamatório,
antibiótico...) já existe no cadastro de item de estoque do tenant
(`Estoque.classificacao_medicamento`) mas nunca chegou ao Painel CowData.
Este campo espelha o mesmo conceito em `MedicamentoComercial` — o fan-out
(`api/routers/painel_cowdata_farmacia.py::_fan_out_medicamento`) copia o
valor pro item de Estoque de cada fazenda-cliente.

Revision ID: a3f1c9d8e6b4
Revises: 9575b6f82b9b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f1c9d8e6b4'
down_revision: Union[str, Sequence[str], None] = '9575b6f82b9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    colunas = {c['name'] for c in insp.get_columns('medicamento_comercial')}
    if 'classificacao_medicamento' not in colunas:
        op.add_column('medicamento_comercial', sa.Column('classificacao_medicamento', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('medicamento_comercial', 'classificacao_medicamento')
