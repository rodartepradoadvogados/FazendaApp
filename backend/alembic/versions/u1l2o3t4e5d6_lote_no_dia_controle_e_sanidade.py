"""lote do dia no controle leiteiro e na aplicação (sanidade/BST)

Espec de Produção (out/2026), decisão 2 do dono: o filtro por lote dos
relatórios é o lote do animal NAQUELA DATA. Daqui pra frente o controle
leiteiro e a aplicação de BST/sanidade gravam o lote do dia; o histórico
antigo fica NULL e o relatório reconstrói pelo MovimentoLote
(fazenda/rules/lote_historico.py). Colunas nullable, sem backfill.

Revision ID: u1l2o3t4e5d6
Revises: t1c2a3r4e5n6
Create Date: 2026-10-23 12:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u1l2o3t4e5d6"
down_revision = "t1c2a3r4e5n6"
branch_labels = None
depends_on = None

TABELAS = ("controle_leiteiro", "sanidade")


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for tabela in TABELAS:
        if not insp.has_table(tabela):
            continue
        colunas = {c["name"] for c in insp.get_columns(tabela)}
        if "lote_no_dia" not in colunas:
            op.add_column(tabela, sa.Column("lote_no_dia", sa.String(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for tabela in TABELAS:
        if not insp.has_table(tabela):
            continue
        colunas = {c["name"] for c in insp.get_columns(tabela)}
        if "lote_no_dia" in colunas:
            with op.batch_alter_table(tabela) as b:
                b.drop_column("lote_no_dia")
