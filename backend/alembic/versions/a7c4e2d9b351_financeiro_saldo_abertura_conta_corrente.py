"""financeiro Fase A (PR 6): saldo de abertura e vínculo da conta corrente por FK

- `conta_corrente.saldo_abertura` (float) e `conta_corrente.data_saldo_abertura` (date): o saldo
  conferido com o extrato numa data (decisão Q12: campo na conta, não lançamento);
- `conta_gerencial.conta_corrente_id` (FK para `conta_corrente.id`, com índice): o vínculo do
  pagamento com a conta, que antes era só o texto livre `conta_bancaria` (continua como rótulo);
- `conta_gerencial.gerado_por` (texto): linha criada automaticamente (retirada do caixa do
  funcionário pelo banco; notas do cartão por item no PR 5).

ADITIVA, idempotente (colunas já criadas pelo `create_all` do boot não abortam o upgrade) e SEM
backfill: nenhuma linha existente é tocada. A ligação do histórico (`conta_corrente_id`) é o
COMANDO `python -m scripts.backfill_conta_corrente` (dry-run por padrão, com log em
`migracao_log_financeiro` e reversão por lote). Nenhum `valor_total`/`valor_pago` muda.
O downgrade remove as colunas (e com elas o que o backfill tiver gravado nelas).

Revision ID: a7c4e2d9b351
Revises: a7c4e2d9f1b3
Create Date: 2026-10-08 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c4e2d9b351'
down_revision: Union[str, Sequence[str], None] = 'a7c4e2d9f1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUNAS_CONTA_CORRENTE = [('saldo_abertura', sa.Float()), ('data_saldo_abertura', sa.Date())]
INDICE_FK = 'ix_conta_gerencial_conta_corrente_id'
FK_NOME = 'fk_conta_gerencial_conta_corrente_id'


def _colunas(insp, tabela):
    return {c['name'] for c in insp.get_columns(tabela)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('conta_corrente'):
        novas = [(n, t) for n, t in COLUNAS_CONTA_CORRENTE if n not in _colunas(insp, 'conta_corrente')]
        if novas:
            with op.batch_alter_table('conta_corrente') as batch:
                for nome, tipo in novas:
                    batch.add_column(sa.Column(nome, tipo, nullable=True))
    if insp.has_table('conta_gerencial'):
        existentes = _colunas(insp, 'conta_gerencial')
        with op.batch_alter_table('conta_gerencial') as batch:
            if 'conta_corrente_id' not in existentes:
                batch.add_column(sa.Column('conta_corrente_id', sa.Integer(), nullable=True))
                batch.create_foreign_key(FK_NOME, 'conta_corrente', ['conta_corrente_id'], ['id'])
            if 'gerado_por' not in existentes:
                batch.add_column(sa.Column('gerado_por', sa.String(), nullable=True))
        indices = {i['name'] for i in sa.inspect(op.get_bind()).get_indexes('conta_gerencial')}
        if INDICE_FK not in indices:
            op.create_index(INDICE_FK, 'conta_gerencial', ['conta_corrente_id'])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table('conta_gerencial'):
        indices = {i['name'] for i in insp.get_indexes('conta_gerencial')}
        if INDICE_FK in indices:
            op.drop_index(INDICE_FK, table_name='conta_gerencial')
        existentes = _colunas(insp, 'conta_gerencial')
        fks = {fk.get('name') for fk in insp.get_foreign_keys('conta_gerencial')}
        sobra = [n for n in ('conta_corrente_id', 'gerado_por') if n in existentes]
        if sobra:
            with op.batch_alter_table('conta_gerencial') as batch:
                if FK_NOME in fks:
                    batch.drop_constraint(FK_NOME, type_='foreignkey')
                for nome in sobra:
                    batch.drop_column(nome)
    if insp.has_table('conta_corrente'):
        sobra = [n for n, _ in COLUNAS_CONTA_CORRENTE if n in _colunas(insp, 'conta_corrente')]
        if sobra:
            with op.batch_alter_table('conta_corrente') as batch:
                for nome in sobra:
                    batch.drop_column(nome)
