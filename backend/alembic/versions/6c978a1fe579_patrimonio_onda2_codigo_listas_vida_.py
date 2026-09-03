"""patrimonio onda2: codigo, vida util estruturada, metodos e baixa

Onda 2 do Motor Financeiro Gerencial. Só ADICIONA colunas opcionais — nenhum
dado existente é alterado ou apagado, e todo item legado continua a ser lido
exatamente como antes (vida útil pelo texto livre, método linear).

Revision ID: 6c978a1fe579
Revises: 8e6a92958536
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6c978a1fe579'
down_revision: Union[str, Sequence[str], None] = '8e6a92958536'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUNAS = (
    ("codigo", sa.String()),
    ("vida_util_anos", sa.Integer()),
    ("vida_util_meses", sa.Integer()),
    ("motivo_baixa", sa.String()),
    ("valor_baixa", sa.Float()),
    ("fator_saldo_decrescente", sa.Float()),
    ("unidades_vida_util_total", sa.Float()),
    ("unidades_consumidas", sa.Float()),
    ("unidade_uso", sa.String()),
)


def upgrade() -> None:
    for nome, tipo in COLUNAS:
        op.add_column("patrimonio", sa.Column(nome, tipo, nullable=True))
    op.create_index("ix_patrimonio_codigo", "patrimonio", ["codigo"])


def downgrade() -> None:
    op.drop_index("ix_patrimonio_codigo", table_name="patrimonio")
    for nome, _tipo in COLUNAS:
        op.drop_column("patrimonio", nome)
