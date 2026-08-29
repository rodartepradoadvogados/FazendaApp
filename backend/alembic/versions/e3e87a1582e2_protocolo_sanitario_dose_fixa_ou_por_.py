"""protocolo sanitario: dose fixa ou por peso vivo

Onda "Protocolo à Mostra". Só ADICIONA colunas opcionais — nenhum dado
existente é alterado aqui. Todo registro legado nasce com
`modo_dose='fixa'` (o default do model), preservando exatamente o
comportamento de hoje; a separação da referência de peso embutida no texto
de `unidade` (ex.: "ml / 15kg PV") é feita depois, sob confirmação, pelo
endpoint report-first POST /cadastro/protocolos-sanitarios/dose-migrar —
nunca por esta migração, que só muda schema.

Revision ID: e3e87a1582e2
Revises: 6c978a1fe579
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3e87a1582e2'
down_revision: Union[str, Sequence[str], None] = '6c978a1fe579'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "protocolo_sanitario_etapa",
        sa.Column("modo_dose", sa.String(), nullable=False, server_default="fixa"),
    )
    op.add_column(
        "protocolo_sanitario_etapa",
        sa.Column("dose_referencia_kg", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("protocolo_sanitario_etapa", "dose_referencia_kg")
    op.drop_column("protocolo_sanitario_etapa", "modo_dose")
