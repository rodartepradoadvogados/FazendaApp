"""protocolo_encerrar_cancelar

Encerramento e cancelamento de um lançamento de protocolo, pela Central de
Protocolos — IATF, indução de lactação e customizado.

- `encerrado_em` / `encerrado_motivo`: o lançamento acabou antes do fim do
  cronograma. As etapas que sobraram continuam gravadas como NÃO realizadas
  (encerrar não é dar por feito o que não foi feito); o que muda é que ele
  para de cobrar pendência na Agenda.
- `ativo`: cancelamento — o lançamento não deveria ter existido. Aqui as
  aplicações voltam a não realizadas e o estoque consumido é estornado.
  `ProtocoloCustomizadoLancamento` já tinha esta coluna; IATF e indução a
  ganham agora, com o mesmo nome e a mesma semântica.

Nota: as colunas de encerramento foram introduzidas em 08/2026 pelo caminho
errado — acrescentadas a `_COLUNAS_NOVAS` em fazenda/database.py, que está
congelado desde a adoção do Alembic. Esta revisão passa a ser a fonte oficial
delas. As adições ao dicionário foram removidas; para os bancos que já
rodaram com aquela versão, o `add_column` abaixo é condicional e não quebra.

Revision ID: b7e4c92f1a08
Revises: 56fb4f344643
Create Date: 2026-08-06 02:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e4c92f1a08'
down_revision: Union[str, Sequence[str], None] = '56fb4f344643'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabela, coluna, tipo, default) — `ativo` do customizado já existe.
COLUNAS = [
    ("protocolo_iatf_lancamento", "encerrado_em", sa.Date(), None),
    ("protocolo_iatf_lancamento", "encerrado_motivo", sa.String(), None),
    ("protocolo_iatf_lancamento", "ativo", sa.Boolean(), sa.true()),
    ("protocolo_inducao_lancamento", "encerrado_em", sa.Date(), None),
    ("protocolo_inducao_lancamento", "encerrado_motivo", sa.String(), None),
    ("protocolo_inducao_lancamento", "ativo", sa.Boolean(), sa.true()),
    ("protocolo_customizado_lancamento", "encerrado_em", sa.Date(), None),
    ("protocolo_customizado_lancamento", "encerrado_motivo", sa.String(), None),
]


def _colunas_existentes(tabela: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if tabela not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(tabela)}


def upgrade() -> None:
    for tabela, coluna, tipo, default in COLUNAS:
        existentes = _colunas_existentes(tabela)
        if not existentes or coluna in existentes:
            # Tabela ainda não criada (banco novo — o create_all a cria com o
            # schema completo) ou coluna já presente (banco que rodou com a
            # versão que passava por _COLUNAS_NOVAS).
            continue
        op.add_column(tabela, sa.Column(coluna, tipo, nullable=True, server_default=default))


def downgrade() -> None:
    for tabela, coluna, _tipo, _default in reversed(COLUNAS):
        existentes = _colunas_existentes(tabela)
        if coluna in existentes:
            op.drop_column(tabela, coluna)
