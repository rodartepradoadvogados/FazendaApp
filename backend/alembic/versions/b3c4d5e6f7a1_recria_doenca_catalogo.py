"""Recria: vincula OcorrenciaClinica/JanelaPontoCritico ao catálogo Doenca

Revision ID: b3c4d5e6f7a1
Revises: a1c2f3d4e5b6
Create Date: 2026-08-07

`JanelaPontoCritico.doenca` e `OcorrenciaClinica.doenca` eram texto livre sem
nenhum vínculo com o catálogo `Doenca` (fazenda/models/sanidade.py). Ganham
`doenca_id` (FK, indexado) por cima — o texto (`doenca`) continua existindo
intacto: é o histórico e o fallback de exibição de quem nunca teve o vínculo
resolvido (ver backfill em fazenda.rules.recria_doenca). Nada é apagado, nada
vira NOT NULL: doenca_id nasce nulo até o backfill (ou uma nova gravação)
preenchê-lo.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a1"
down_revision: Union[str, Sequence[str], None] = "a1c2f3d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABELAS_COLUNA_DOENCA_ID = ["ocorrencia_clinica", "janela_ponto_critico"]


def _colunas_existentes(tabela: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(tabela)}


def _indices_existentes(tabela: str) -> set[str]:
    bind = op.get_bind()
    return {ix["name"] for ix in sa.inspect(bind).get_indexes(tabela)}


def upgrade() -> None:
    # Add-missing: o repo tem auto-heal de schema no boot (database.py), então
    # a coluna pode já existir quando esta migração rodar — ver mesma nota em
    # a1c2f3d4e5b6_farmacia_indicacoes_carencia.py.
    for tabela in _TABELAS_COLUNA_DOENCA_ID:
        if "doenca_id" not in _colunas_existentes(tabela):
            op.add_column(tabela, sa.Column("doenca_id", sa.Integer(), nullable=True))
        indice = f"ix_{tabela}_doenca_id"
        if indice not in _indices_existentes(tabela):
            op.create_index(indice, tabela, ["doenca_id"], unique=False)


def downgrade() -> None:
    for tabela in _TABELAS_COLUNA_DOENCA_ID:
        indice = f"ix_{tabela}_doenca_id"
        if indice in _indices_existentes(tabela):
            op.drop_index(indice, table_name=tabela)
        if "doenca_id" in _colunas_existentes(tabela):
            op.drop_column(tabela, "doenca_id")
