"""caixa dos funcionarios: comprovante da retirada e do pagamento direto do rateio

`caixa_movimento.comprovante_anexo_id` (PessoaAnexo) e, na linha do rateio, `numero_documento_pagamento` e
`comprovante_anexo_id` — copiados para a retirada quando o rateio e confirmado. ADITIVA e idempotente.

Revision ID: d2b6f0a4e813
Revises: c1a5e9b3d742
Create Date: 2026-10-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2b6f0a4e813'
down_revision: Union[str, Sequence[str], None] = 'c1a5e9b3d742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUNAS = {
    'caixa_movimento': [('comprovante_anexo_id', sa.Integer())],
    'caixa_rateio_linha': [('numero_documento_pagamento', sa.String()), ('comprovante_anexo_id', sa.Integer())],
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for tabela, colunas in COLUNAS.items():
        if not insp.has_table(tabela):
            continue
        existentes = {c['name'] for c in insp.get_columns(tabela)}
        novas = [(n, t) for n, t in colunas if n not in existentes]
        if novas:
            with op.batch_alter_table(tabela) as batch:
                for nome, tipo in novas:
                    batch.add_column(sa.Column(nome, tipo, nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for tabela, colunas in COLUNAS.items():
        if not insp.has_table(tabela):
            continue
        existentes = {c['name'] for c in insp.get_columns(tabela)}
        sobra = [n for n, _ in colunas if n in existentes]
        if sobra:
            with op.batch_alter_table(tabela) as batch:
                for nome in sobra:
                    batch.drop_column(nome)
