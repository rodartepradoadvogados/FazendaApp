"""financeiro Fase A (PR 0 + PR 1): natureza_fin, patrimonio.centro_custo e log de backfill

- `conta_gerencial.natureza_fin`, `lancamento_item.natureza_fin`, `plano_conta_gerencial.natureza_fin`
  (natureza econômica do lançamento — ver fazenda/rules/natureza.py);
- `patrimonio.centro_custo` (depreciação por centro de custo);
- tabela `migracao_log_financeiro` (o que cada backfill mudou, antes/depois, por fazenda e lote —
  é por ela que um lote é revertido; ver fazenda/rules/migracao_log.py).

ADITIVA, idempotente (colunas/tabela já criadas pelo `create_all` do boot não abortam o upgrade) e
SEM backfill: nenhuma linha existente é tocada. O preenchimento do histórico é um COMANDO separado
(`python -m scripts.backfill_natureza_fin`, dry-run por padrão), nunca esta migração.

Revision ID: e5a9c3f1b742
Revises: d2b6f0a4e813
Create Date: 2026-10-08 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5a9c3f1b742'
down_revision: Union[str, Sequence[str], None] = 'd2b6f0a4e813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUNAS = {
    'conta_gerencial': [('natureza_fin', sa.String())],
    'lancamento_item': [('natureza_fin', sa.String())],
    'plano_conta_gerencial': [('natureza_fin', sa.String())],
    'patrimonio': [('centro_custo', sa.String())],
}

TABELA_LOG = 'migracao_log_financeiro'
INDICES_LOG = (
    ('ix_migracao_log_financeiro_fazenda_id', ['fazenda_id']),
    ('ix_migracao_log_financeiro_lote', ['lote']),
    ('ix_migracao_log_financeiro_migracao', ['migracao']),
)


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

    if not insp.has_table(TABELA_LOG):
        op.create_table(
            TABELA_LOG,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('fazenda_id', sa.Integer(), sa.ForeignKey('fazenda.id'), nullable=True),
            sa.Column('lote', sa.String(), nullable=False),
            sa.Column('migracao', sa.String(), nullable=False),
            sa.Column('tabela', sa.String(), nullable=False),
            sa.Column('registro_id', sa.Integer(), nullable=False),
            sa.Column('campo', sa.String(), nullable=False),
            sa.Column('valor_antes', sa.String(), nullable=True),
            sa.Column('valor_depois', sa.String(), nullable=True),
            sa.Column('motivo', sa.String(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('revertido_em', sa.DateTime(), nullable=True),
        )
    existentes_idx = {i['name'] for i in sa.inspect(op.get_bind()).get_indexes(TABELA_LOG)}
    for nome, colunas in INDICES_LOG:
        if nome not in existentes_idx:
            op.create_index(nome, TABELA_LOG, colunas)


def downgrade() -> None:
    """Desfaz a migração inteira. Atenção: remover `natureza_fin` desfaz também
    qualquer backfill de natureza já aplicado (o dado só existia nas colunas
    novas), e o log vai junto. Para desfazer só UM lote de backfill, sem
    descer a migração, use `python -m scripts.backfill_natureza_fin --reverter LOTE`."""
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABELA_LOG):
        existentes_idx = {i['name'] for i in insp.get_indexes(TABELA_LOG)}
        for nome, _colunas in INDICES_LOG:
            if nome in existentes_idx:
                op.drop_index(nome, table_name=TABELA_LOG)
        op.drop_table(TABELA_LOG)
    for tabela, colunas in COLUNAS.items():
        if not insp.has_table(tabela):
            continue
        existentes = {c['name'] for c in insp.get_columns(tabela)}
        sobra = [n for n, _ in colunas if n in existentes]
        if sobra:
            with op.batch_alter_table(tabela) as batch:
                for nome in sobra:
                    batch.drop_column(nome)
