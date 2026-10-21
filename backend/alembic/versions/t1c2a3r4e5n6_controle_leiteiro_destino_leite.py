"""controle leiteiro: destino do leite (tanque/descarte) — carência sanitária (D4)

Fase F5 do Sanitário Preventivo v2: no lançamento de produção por vaca, a
vaca em carência de leite segue o modo decidido na caixa (bloqueio recusa;
descarte grava o controle como DESCARTE, fora do tanque; tanque segue normal
com log). `destino_leite` NULL = tanque (todo o histórico anterior).
`sanitario_registro_id` aponta o registro sanitário que causou o descarte.

Revision ID: t1c2a3r4e5n6
Revises: s1n2o3v4o5m6
Create Date: 2026-10-21 21:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t1c2a3r4e5n6"
down_revision = "s1n2o3v4o5m6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("controle_leiteiro"):
        return
    colunas = {c["name"] for c in insp.get_columns("controle_leiteiro")}
    if "destino_leite" not in colunas:
        op.add_column("controle_leiteiro", sa.Column("destino_leite", sa.String(), nullable=True))
    if "sanitario_registro_id" not in colunas:
        op.add_column("controle_leiteiro", sa.Column("sanitario_registro_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    colunas = {c["name"] for c in insp.get_columns("controle_leiteiro")}
    with op.batch_alter_table("controle_leiteiro") as b:
        if "sanitario_registro_id" in colunas:
            b.drop_column("sanitario_registro_id")
        if "destino_leite" in colunas:
            b.drop_column("destino_leite")
