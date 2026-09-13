"""lote.modo_baixa_estoque e consumo_alimento.baixou_estoque

Proposta aceita pelo proprietário: escolher, POR LOTE, como a dieta afeta o
Estoque — "automática pela dieta" (baixa dia a dia pelo PLANO, mecanismo já
existente em `_dar_baixa_automatica`), "pelo consumo real" (só baixa quando
alguém lança o consumo de verdade em "Consumo diário e sobra") ou "sem baixa"
(a dieta é só plano/receita, nunca mexe em estoque).

`lote.modo_baixa_estoque` nasce "consumo_real": é o ÚNICO mecanismo que já
funciona hoje de ponta a ponta, então todo lote existente antes desta coluna
continua se comportando exatamente como antes — a baixa automática por dias
decorridos passa a exigir opt-in explícito ("automatica") por lote, ao invés
de rodar incondicionalmente pra toda a fazenda como fazia até aqui.

`consumo_alimento.baixou_estoque` nasce `true`: toda linha existente debitou
estoque incondicionalmente ao ser criada (era o único comportamento que
existia). Guardado no REGISTRO, não recalculado do modo atual do lote, porque
o modo pode mudar depois — a exclusão de um lançamento tem de saber se
estorna olhando pro que aconteceu quando foi feito, não pro que o lote é hoje.

Duas colunas, uma migração só: nascem juntas da mesma proposta.

Revision ID: dae0e0884347
Revises: f4a7b8c9d1e3
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dae0e0884347'
down_revision: Union[str, Sequence[str], None] = 'f4a7b8c9d1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Idempotente por coluna (`has_column`), como as demais migrações aditivas
    deste repositório — um banco de dev/teste pode já ter a coluna via
    `create_all` antes do Alembic chegar.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas_lote = {c['name'] for c in insp.get_columns('lote')} if insp.has_table('lote') else set()
    if 'modo_baixa_estoque' not in colunas_lote:
        with op.batch_alter_table('lote', schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'modo_baixa_estoque', sa.String(), nullable=False, server_default='consumo_real',
            ))

    colunas_consumo = {c['name'] for c in insp.get_columns('consumo_alimento')} if insp.has_table('consumo_alimento') else set()
    if 'baixou_estoque' not in colunas_consumo:
        with op.batch_alter_table('consumo_alimento', schema=None) as batch_op:
            batch_op.add_column(sa.Column(
                'baixou_estoque', sa.Boolean(), nullable=False, server_default=sa.true(),
            ))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas_consumo = {c['name'] for c in insp.get_columns('consumo_alimento')} if insp.has_table('consumo_alimento') else set()
    if 'baixou_estoque' in colunas_consumo:
        with op.batch_alter_table('consumo_alimento', schema=None) as batch_op:
            batch_op.drop_column('baixou_estoque')

    colunas_lote = {c['name'] for c in insp.get_columns('lote')} if insp.has_table('lote') else set()
    if 'modo_baixa_estoque' in colunas_lote:
        with op.batch_alter_table('lote', schema=None) as batch_op:
            batch_op.drop_column('modo_baixa_estoque')
