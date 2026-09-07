"""vale_parcela: natureza da assunção (o que a fazenda assumiu, e como)

O QUE ESTA MIGRAÇÃO FECHA. `reverter_desconsideracao` (PR #720/#722) RECUSA
quando não consegue distinguir o que `_assumir_no_financeiro` fez no momento
em que a fazenda assumiu o valor. Um vale sem item de nota vinculado HOJE e
sem lançamento próprio pode ser duas coisas opostas:

  a) "sem lastro" — vale lançado à mão com forma `desconto_integral_folha`,
     em que nada saiu do caixa e nada foi tocado no Financeiro: reverter é só
     tirar a marca da parcela; ou
  b) "item de nota cujo vínculo foi SOLTO na assunção" — o item voltou aos
     relatórios gerenciais como despesa da fazenda, e reverter sem religar o
     vínculo contaria a MESMA despesa duas vezes (o item como gasto da
     fazenda e o desconto do funcionário).

`limpar_vinculo_de_itens` não deixa marca nenhuma, então os dois ficam
idênticos depois — e chutar mexe em dinheiro de gente real. A saída é parar
de deduzir e passar a GRAVAR, no ato da assunção, o que ela fez:

- `vale_parcela.natureza_assuncao`: "item_de_nota" | "lancamento_proprio" |
  "sem_lastro" — os mesmos valores que `_assumir_no_financeiro` já devolve.
- `vale_parcela.assuncao_detalhe`: JSON com o resto — qual AÇÃO assumiu a
  parcela ("desconsiderar_mes" | "cancelar" | "pagamento_folha"), o nº do
  lançamento envolvido, se ele foi reclassificado e quais itens de nota
  foram divididos (e por qual gêmeo). É a ação gravada aqui que permite a
  `reverter_cancelamento` devolver SÓ o que o cancelamento varreu, sem
  ressuscitar a cobrança de um mês que o dono já havia desconsiderado antes.

AS DUAS SÃO NULLABLE E SEM `server_default`, de propósito:
- linha antiga fica com NULL, que significa "natureza desconhecida" e
  CONTINUA caindo na recusa por ambiguidade — inventar natureza para o
  passado é exatamente o erro que a coluna existe para evitar;
- sem `server_default` não há reescrita da tabela inteira no upgrade, que
  roda no BOOT da API (`database.py::_aplicar_alembic`) em produção.

A coluna resolve a AMBIGUIDADE, não torna tudo reversível: assunção de
natureza "item_de_nota" continua sendo recusada, porque o item pode ter sido
editado depois e juntar as duas linhas às cegas corromperia a nota fiscal.

Revision ID: b7d21f9c4a30
Revises: a4f8c1d92e07
Create Date: 2026-09-07 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d21f9c4a30'
down_revision: Union[str, Sequence[str], None] = 'a4f8c1d92e07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Idempotente (`sa.inspect` antes de cada `add_column`), pelo mesmo motivo
    da migração a1c4e7b93f52: `database.py` chama `SQLModel.metadata.
    create_all` na subida da aplicação. Se a app subir antes de o
    `alembic upgrade head` terminar — o que acontece em deploy —, as colunas
    novas já existem e um `add_column` cru aborta o upgrade INTEIRO, deixando
    a API fora do ar.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas = {c['name'] for c in insp.get_columns('vale_parcela')}
    if 'natureza_assuncao' not in colunas:
        op.add_column('vale_parcela', sa.Column('natureza_assuncao', sa.String(), nullable=True))
    if 'assuncao_detalhe' not in colunas:
        op.add_column('vale_parcela', sa.Column('assuncao_detalhe', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('vale_parcela', 'assuncao_detalhe')
    op.drop_column('vale_parcela', 'natureza_assuncao')
