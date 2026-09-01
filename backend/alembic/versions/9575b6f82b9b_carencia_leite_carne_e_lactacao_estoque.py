"""estoque: carencia_leite_dias/carencia_carne_dias/proibido_lactacao

Pedido do usuário (01/09/2026): "precisa de colocar, junto com a carência
para o leite, opção de marcar se pode aplicar em vacas em lactação ou não" —
hoje `Estoque.carencia_dias` é um único campo genérico (sem separar leite de
carne) e não existe nenhuma flag de lactação no item de estoque do tenant
(só existe em MedicamentoComercial, o catálogo do Painel CowData, sem nunca
chegar ao item de estoque de verdade). `carencia_dias` continua existindo
(compatibilidade com quem já lê esse campo); os três novos passam a ser a
fonte de verdade a partir de agora (ver models/estoque.py::Estoque e o
fan-out em api/routers/painel_cowdata_farmacia.py).

Revision ID: 9575b6f82b9b
Revises: 5a8900b64337
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9575b6f82b9b'
down_revision: Union[str, Sequence[str], None] = '5a8900b64337'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    colunas = {c['name'] for c in insp.get_columns('estoque')}

    if 'carencia_leite_dias' not in colunas:
        op.add_column('estoque', sa.Column('carencia_leite_dias', sa.Integer(), nullable=True))
    if 'carencia_carne_dias' not in colunas:
        op.add_column('estoque', sa.Column('carencia_carne_dias', sa.Integer(), nullable=True))
    if 'proibido_lactacao' not in colunas:
        op.add_column('estoque', sa.Column('proibido_lactacao', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('estoque', 'proibido_lactacao')
    op.drop_column('estoque', 'carencia_carne_dias')
    op.drop_column('estoque', 'carencia_leite_dias')
