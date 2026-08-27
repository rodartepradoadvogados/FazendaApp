"""plano_conta_linha_dre

DRE Gerencial em cascata (Onda 3a — backend) — nova coluna
`plano_conta_gerencial.linha_dre`: em qual das 15 linhas clássicas da DRE
(ver fazenda/rules/dre.py) a conta se classifica, ou o valor especial
"NAO_ENTRA_NA_DRE" para conta que legitimamente fica fora do resultado
(ex.: principal de financiamento — nunca despesa, ver ADR em rules/dre.py).

Nasce NULA para toda conta já cadastrada — a classificação é decisão do
usuário (feita aos poucos pela tela de conferência, GET
/financeiro/dre/conferencia), não algo que a migração deva adivinhar linha a
linha. ÚNICA exceção, por ser mapeamento seguro e óbvio: conta já marcada
`rmca_receita_leite=True` (receita de leite, ver Configurações > Parâmetros
financeiros > RMCA) nasce direto com `linha_dre='RECEITA_VENDAS'` — é
receita de venda por definição, não há ambiguidade a resolver.

Revision ID: 8e6a92958536
Revises: 3bd371891acd
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e6a92958536'
down_revision: Union[str, Sequence[str], None] = '3bd371891acd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELA = "plano_conta_gerencial"
_COLUNA = "linha_dre"


def _colunas_existentes(tabela: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if tabela not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(tabela)}


def upgrade() -> None:
    existentes = _colunas_existentes(_TABELA)
    if not existentes:
        # Tabela ainda não criada (banco novo) — o create_all a cria com o
        # schema completo, coluna incluída; nada a fazer aqui.
        return
    if _COLUNA not in existentes:
        op.add_column(_TABELA, sa.Column(_COLUNA, sa.String(), nullable=True))

    # Único seed automático aceito (ver docstring do módulo): receita de
    # leite já marcada para o RMCA sempre é RECEITA_VENDAS na DRE — não há
    # decisão nenhuma do usuário a atropelar aqui. Idempotente: só afeta
    # quem ainda está nulo.
    op.execute(
        sa.text(
            f"UPDATE {_TABELA} SET {_COLUNA} = 'RECEITA_VENDAS' "
            f"WHERE rmca_receita_leite = true AND {_COLUNA} IS NULL"
        )
    )


def downgrade() -> None:
    existentes = _colunas_existentes(_TABELA)
    if _COLUNA in existentes:
        op.drop_column(_TABELA, _COLUNA)
