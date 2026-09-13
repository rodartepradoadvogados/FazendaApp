"""pessoa: vale-alimentação como configuração do funcionário

O QUE ESTA MIGRAÇÃO ABRE. O vale-alimentação deixou de ser uma rubrica que
alguém lançaria mês a mês (desenho recusado, porque a natureza da verba depende
da forma de pagamento) e passou a ser CONFIGURAÇÃO DO VÍNCULO, nas palavras do
dono: "não precisa de uma rubrica para vale alimentação, só precisa de ter como
cadastrar se vai ter ou não e o valor-base, se diário ou mensal, se pago
antecipado ou vencido, para fins de competência, e o valor. O resto é padrão."

São quatro colunas em `pessoa`, e a folha lê as quatro para GERAR a linha do
holerite sozinha (ver `fazenda/rules/vale_alimentacao.py`):

- `vale_alimentacao`               — tem ou não tem;
- `vale_alimentacao_valor`         — o valor-base, em reais;
- `vale_alimentacao_periodicidade` — "diario" (× dias da competência) |
                                     "mensal" (valor cheio);
- `vale_alimentacao_regime`        — "vencido" (o VA da competência sai na
                                     folha da própria competência) |
                                     "antecipado" (o VA de uma competência é
                                     pago junto com a folha da ANTERIOR).

POR QUE OS DEFAULTS SÃO ESTES:
- a flag nasce `false` com `server_default` constante — ninguém que já está
  cadastrado passa a ter vale-alimentação por causa de um deploy, e um default
  constante não obriga reescrita da tabela no Postgres (a migração roda no BOOT
  da API, em `database.py::_aplicar_alembic`);
- as outras três são NULLABLE e SEM `server_default`: sem a flag ligada elas
  não significam nada, e as regras já normalizam o nulo para o padrão
  conservador ("mensal" e "vencido", que não deslocam dinheiro para mês
  nenhum) — ver `periodicidade_valida`/`regime_valido`.

`vale_alimentacao_valor` é Float pelo mesmo motivo de `pessoa.salario_base` e
de `folha_rubrica.valor`: o projeto inteiro guarda dinheiro em Float e arredonda
em duas casas na regra. Trocar o tipo só nesta coluna criaria uma exceção que
todo somatório teria de conhecer.

Revision ID: c3e91b47da28
Revises: b7d21f9c4a30
Create Date: 2026-09-07 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e91b47da28'
down_revision: Union[str, Sequence[str], None] = 'b7d21f9c4a30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Idempotente (`sa.inspect` antes de cada `add_column`), pelo mesmo motivo da
    migração b7d21f9c4a30: `database.py` chama `SQLModel.metadata.create_all` na
    subida da aplicação. Se a app subir antes de o `alembic upgrade head`
    terminar — o que acontece em deploy —, as colunas novas já existem e um
    `add_column` cru aborta o upgrade INTEIRO, deixando a API fora do ar.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas = {c['name'] for c in insp.get_columns('pessoa')}
    if 'vale_alimentacao' not in colunas:
        op.add_column('pessoa', sa.Column(
            'vale_alimentacao', sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
    if 'vale_alimentacao_valor' not in colunas:
        op.add_column('pessoa', sa.Column('vale_alimentacao_valor', sa.Float(), nullable=True))
    if 'vale_alimentacao_periodicidade' not in colunas:
        op.add_column('pessoa', sa.Column('vale_alimentacao_periodicidade', sa.String(), nullable=True))
    if 'vale_alimentacao_regime' not in colunas:
        op.add_column('pessoa', sa.Column('vale_alimentacao_regime', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema.

    Desfaz só o que o upgrade acrescentou. As linhas de holerite já geradas
    (`folha_rubrica` com código `vale_alimentacao`) NÃO são apagadas de
    propósito: elas são o recibo do que foi pago, e um downgrade de esquema não
    pode reescrever documento trabalhista emitido.
    """
    op.drop_column('pessoa', 'vale_alimentacao_regime')
    op.drop_column('pessoa', 'vale_alimentacao_periodicidade')
    op.drop_column('pessoa', 'vale_alimentacao_valor')
    op.drop_column('pessoa', 'vale_alimentacao')
