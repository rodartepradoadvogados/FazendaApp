"""tratos por dieta (% de cada trato + posição da leitura da sobra), trato no consumo e ciclo da sobra

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-10-21 00:00:00.000000

Todas as colunas são NULLABLE e nascem vazias: NULL é o comportamento de
sempre (dieta = 2 tratos 50/50, consumo lançado por dia, sobra comparada com o
fornecido do próprio dia). Nenhum dado existente é reescrito — ver
fazenda/rules/tratos.py.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "n5o6p7q8r9s0"
down_revision = "m4n5o6p7q8r9"
branch_labels = None
depends_on = None

COLUNAS = {
    "dieta_lancamento": [
        ("tratos_pct", sa.String()),
        ("sobra_posicao_leitura", sa.Integer()),
    ],
    "consumo_alimento": [
        ("trato", sa.Integer()),
    ],
    "consumo_sobra": [
        ("data_leitura", sa.Date()),
        ("posicao_leitura", sa.Integer()),
        ("tratos_pct", sa.String()),
    ],
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for tabela, colunas in COLUNAS.items():
        if not insp.has_table(tabela):
            continue  # a tabela inteira ainda vai ser criada com o schema completo
        existentes = {c["name"] for c in insp.get_columns(tabela)}
        for nome, tipo in colunas:
            if nome not in existentes:
                op.add_column(tabela, sa.Column(nome, tipo, nullable=True))


def downgrade() -> None:
    for tabela, colunas in COLUNAS.items():
        for nome, _ in reversed(colunas):
            op.drop_column(tabela, nome)
