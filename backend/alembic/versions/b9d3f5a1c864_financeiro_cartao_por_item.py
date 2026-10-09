"""financeiro Fase A (PR 5): cartão de crédito por item

- `conta_gerencial.fatura_cartao_id` (FK para `fatura_cartao.id`, com índice): a nota de cada compra
  no cartão aponta a fatura que a paga;
- `fatura_cartao.valor_pago` e `fatura_cartao.desconto_acrescimo` (float): o pago e a diferença
  rateada entre as notas;
- `lancamento_cartao.numero_lancamento` (texto, com índice): a nota da compra.

ADITIVA, idempotente (colunas já criadas pelo `create_all` do boot não abortam o upgrade) e SEM
backfill. As notas do histórico são o COMANDO `python -m scripts.backfill_cartao_por_item`
(dry-run por padrão; com log em `migracao_log_financeiro` e reversão por lote; nunca duplica o
saldo: a nota de fatura já paga nasce sem conta bancária e fora do caixa). O downgrade remove as
colunas — as notas criadas pelo backfill ficam como lançamentos comuns: reverta o lote ANTES.

Revision ID: b9d3f5a1c864
Revises: a7c4e2d9b351
Create Date: 2026-10-09 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9d3f5a1c864'
down_revision: Union[str, Sequence[str], None] = 'a7c4e2d9b351'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUNAS_FATURA = [('valor_pago', sa.Float()), ('desconto_acrescimo', sa.Float())]
FK_NOME = 'fk_conta_gerencial_fatura_cartao_id'
INDICES = (
    ('conta_gerencial', 'ix_conta_gerencial_fatura_cartao_id', 'fatura_cartao_id'),
    ('lancamento_cartao', 'ix_lancamento_cartao_numero_lancamento', 'numero_lancamento'),
)


def _colunas(insp, tabela):
    return {c['name'] for c in insp.get_columns(tabela)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('conta_gerencial') and 'fatura_cartao_id' not in _colunas(insp, 'conta_gerencial'):
        with op.batch_alter_table('conta_gerencial') as batch:
            batch.add_column(sa.Column('fatura_cartao_id', sa.Integer(), nullable=True))
            batch.create_foreign_key(FK_NOME, 'fatura_cartao', ['fatura_cartao_id'], ['id'])
    if insp.has_table('fatura_cartao'):
        novas = [(n, t) for n, t in COLUNAS_FATURA if n not in _colunas(insp, 'fatura_cartao')]
        if novas:
            with op.batch_alter_table('fatura_cartao') as batch:
                for nome, tipo in novas:
                    batch.add_column(sa.Column(nome, tipo, nullable=True))
    if insp.has_table('lancamento_cartao') and 'numero_lancamento' not in _colunas(insp, 'lancamento_cartao'):
        with op.batch_alter_table('lancamento_cartao') as batch:
            batch.add_column(sa.Column('numero_lancamento', sa.String(), nullable=True))
    insp = sa.inspect(op.get_bind())
    for tabela, indice, coluna in INDICES:
        if insp.has_table(tabela) and indice not in {i['name'] for i in insp.get_indexes(tabela)}:
            op.create_index(indice, tabela, [coluna])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for tabela, indice, _coluna in INDICES:
        if insp.has_table(tabela) and indice in {i['name'] for i in insp.get_indexes(tabela)}:
            op.drop_index(indice, table_name=tabela)
    if insp.has_table('conta_gerencial') and 'fatura_cartao_id' in _colunas(insp, 'conta_gerencial'):
        fks = {fk.get('name') for fk in insp.get_foreign_keys('conta_gerencial')}
        with op.batch_alter_table('conta_gerencial') as batch:
            if FK_NOME in fks:
                batch.drop_constraint(FK_NOME, type_='foreignkey')
            batch.drop_column('fatura_cartao_id')
    if insp.has_table('fatura_cartao'):
        sobra = [n for n, _ in COLUNAS_FATURA if n in _colunas(insp, 'fatura_cartao')]
        if sobra:
            with op.batch_alter_table('fatura_cartao') as batch:
                for nome in sobra:
                    batch.drop_column(nome)
    if insp.has_table('lancamento_cartao') and 'numero_lancamento' in _colunas(insp, 'lancamento_cartao'):
        with op.batch_alter_table('lancamento_cartao') as batch:
            batch.drop_column('numero_lancamento')
