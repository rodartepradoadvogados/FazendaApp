"""raca/grau_sangue: campo nota (texto didatico do seletor)

Adiciona `raca.nota` e `grau_sangue_cadastro.nota` — texto curto explicando
o que cada raça/grau de sangue significa, mostrado como subtítulo no
seletor de busca da ficha do animal (ver frontend/components/
ListaFechadaPicker.tsx). Puramente aditivo: não mexe em nenhuma linha
existente, e os dois cadastros continuam funcionando sem nota (campo
opcional) até o seed/edição preencher.

Revision ID: 60eb25ade4b1
Revises: e3ad0b2a1c47
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '60eb25ade4b1'
down_revision: Union[str, Sequence[str], None] = 'e3ad0b2a1c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # Guarda de idempotência: o `create_all` de subida pode já ter criado a
    # coluna com o schema atual do model antes desta migração rodar — mesmo
    # padrão de e3ad0b2a1c47_protocolo_sanitario_lote.py.
    colunas_raca = {c["name"] for c in insp.get_columns("raca")}
    if "nota" not in colunas_raca:
        op.add_column("raca", sa.Column("nota", sa.String(), nullable=True))

    colunas_grau = {c["name"] for c in insp.get_columns("grau_sangue_cadastro")}
    if "nota" not in colunas_grau:
        op.add_column("grau_sangue_cadastro", sa.Column("nota", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("grau_sangue_cadastro", "nota")
    op.drop_column("raca", "nota")
