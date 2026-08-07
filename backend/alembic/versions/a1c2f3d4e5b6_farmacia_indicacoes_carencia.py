"""Farmácia: indicação (doença ou manejo), bula e carência leite/carne

Revision ID: a1c2f3d4e5b6
Revises: f5453c5a86ac
Create Date: 2026-08-07

Prepara o catálogo unificado da Farmácia:

- `doenca` vira INDICAÇÃO (ganha `tipo`): doença ou manejo reprodutivo/produtivo.
  O nome da tabela e das linhas já semeadas NÃO muda — renomear quebraria
  `PrincipioAtivo.doenca_id`, `ProtocoloSanitarioEtapa` gravada por critério e o
  casamento por nome das vacinas pré-parto em routers/estoque.py.
- `medicamento_comercial` passa a guardar a bula: uso, dose, via, concentração,
  link e — o que mais importa numa fazenda de leite — CARÊNCIA separada em
  leite e carne, além das flags de proibição em lactação e risco na gestação.
- `indicacao_terapeutica` ganha `fazenda_id` na unique: sem isso a 2ª fazenda a
  personalizar a mesma indicação batia em IntegrityError ao clonar o padrão.

Nada é apagado e nada vira NOT NULL: todo campo novo nasce nulo, e nulo em
carência significa "não informada" (nunca "zero/liberado").
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c2f3d4e5b6"
down_revision: Union[str, Sequence[str], None] = "f5453c5a86ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUNAS_DOENCA = [
    ("tipo", sa.String()),
    ("descricao", sa.String()),
    ("origem_id", sa.Integer()),
]

COLUNAS_MEDICAMENTO = [
    ("uso_principal", sa.String()),
    ("concentracao", sa.String()),
    ("dose_padrao", sa.Float()),
    ("unidade_dose", sa.String()),
    ("dose_base", sa.String()),
    ("dose_referencia_kg", sa.Float()),
    ("dose_texto", sa.String()),
    ("via_padrao", sa.String()),
    ("link_bula", sa.String()),
    ("carencia_leite_dias", sa.Integer()),
    ("carencia_carne_dias", sa.Integer()),
    ("proibido_lactacao", sa.Boolean()),
    ("alerta_gestacao", sa.Boolean()),
    ("alerta", sa.String()),
    ("origem_id", sa.Integer()),
]

COLUNAS_INDICACAO = [
    ("nota", sa.String()),
    ("origem_id", sa.Integer()),
]


def _colunas_existentes(tabela: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(tabela)}


def _add(tabela: str, colunas) -> None:
    """Add-missing: só cria a coluna que ainda não existe. O repo tem auto-heal
    de schema no boot (database.py), então a coluna pode já ter sido criada por
    lá antes desta migração rodar — nesse caso `add_column` estouraria."""
    existentes = _colunas_existentes(tabela)
    for nome, tipo in colunas:
        if nome not in existentes:
            op.add_column(tabela, sa.Column(nome, tipo, nullable=True))


def _drop(tabela: str, colunas) -> None:
    existentes = _colunas_existentes(tabela)
    for nome, _ in colunas:
        if nome in existentes:
            op.drop_column(tabela, nome)


def upgrade() -> None:
    _add("doenca", COLUNAS_DOENCA)
    _add("medicamento_comercial", COLUNAS_MEDICAMENTO)
    _add("indicacao_terapeutica", COLUNAS_INDICACAO)

    # Toda doença que já existe é doença de verdade (o tipo só passa a variar
    # com o seed novo das indicações de manejo).
    op.execute("UPDATE doenca SET tipo = 'doenca' WHERE tipo IS NULL")

    # Unique de indicação passa a incluir fazenda_id. `batch_alter_table` é
    # obrigatório no SQLite (não altera constraint no lugar) — a tabela está
    # vazia em produção, então a recriação é barata e sem risco de perda.
    with op.batch_alter_table("indicacao_terapeutica") as batch:
        try:
            batch.drop_constraint("uq_indicacao_principio_doenca", type_="unique")
        except Exception:
            # Banco criado por `SQLModel.metadata.create_all` (dev/teste) pode
            # não ter a constraint nomeada — seguir em frente e só criar a nova.
            pass
        batch.create_unique_constraint(
            "uq_indicacao_principio_doenca", ["principio_ativo_id", "doenca_id", "fazenda_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("indicacao_terapeutica") as batch:
        try:
            batch.drop_constraint("uq_indicacao_principio_doenca", type_="unique")
        except Exception:
            pass
        batch.create_unique_constraint("uq_indicacao_principio_doenca", ["principio_ativo_id", "doenca_id"])

    _drop("indicacao_terapeutica", COLUNAS_INDICACAO)
    _drop("medicamento_comercial", COLUNAS_MEDICAMENTO)
    _drop("doenca", COLUNAS_DOENCA)
