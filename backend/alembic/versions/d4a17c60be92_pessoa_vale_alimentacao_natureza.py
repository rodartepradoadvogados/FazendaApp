"""pessoa: forma de pagamento do vale-alimentação e a trava da OJ 413

O QUE ESTA MIGRAÇÃO ABRE, e por que ela existe. O cadastro de vale-alimentação
(c3e91b47da28) sabia dizer QUANTO e DE QUE MÊS, mas não sabia responder a
pergunta que decide dinheiro de verdade: **o vale-alimentação entra ou não na
base de INSS, FGTS, 13º e férias?** Essa resposta não depende do valor nem da
periodicidade — depende de COMO o benefício é pago, e de a fazenda estar ou não
no PAT. Enquanto o campo não existia, o sistema assumia o padrão do PAT
(indenizatório) para todo mundo, e a ressalva ficava escrita no código: quem
pagasse em dinheiro estaria com a base SUBDECLARADA.

São duas colunas em `pessoa`:

- `vale_alimentacao_forma` — "dinheiro" | "cartao" | "in_natura". Sem padrão
  adivinhado: o cadastro passa a EXIGIR a escolha quando o benefício está
  ligado, e a regra trata o nulo como "não sei", enquadrando como salarial (o
  lado que não subdeclara base). Assumir "cartão" em silêncio tiraria da base
  do INSS e do FGTS uma verba que, paga em dinheiro, tem de entrar.

- `vale_alimentacao_natureza_travada_salarial` — a OJ 413 da SDI-1 do TST
  virada coluna: "a pactuação em norma coletiva conferindo caráter
  indenizatório à verba 'auxílio-alimentação' ou a adesão posterior do
  empregador ao PAT não altera a natureza salarial da parcela, instituída
  anteriormente, para aqueles empregados que, habitualmente, já percebiam o
  benefício". Ligada, a natureza é salarial independentemente da forma e do
  PAT. É marcador POR FUNCIONÁRIO porque a mesma fazenda pode ter duas
  populações com regras diferentes na mesma folha (CLT, art. 468).

O PAT é fato da FAZENDA, não do funcionário, e por isso NÃO está aqui: mora em
`parametro_fazenda` (chave `inscrita_no_pat`), junto dos três parâmetros de
contagem de dias do benefício — ver `fazenda/rules/parametros.py`. Parâmetro
não precisa de migração; o seed do startup cria a linha que faltar.

POR QUE AS DUAS COLUNAS SÃO NULLABLE E SEM `server_default`. A migração roda no
BOOT da API (`database.py::_aplicar_alembic`), e um `server_default` num
`ALTER TABLE ADD COLUMN` obriga o Postgres a reescrever a tabela inteira antes
de a API subir. NULL é, além disso, a informação CERTA para o passado: ninguém
sabe em que forma a fazenda vinha pagando o benefício antes de existir o campo,
e é justamente por não saber que a regra enquadra como salarial até alguém
abrir o cadastro e escolher.

NENHUM BACKFILL, e a ausência é decisão. Carimbar "cartao" em quem já tinha o
benefício ligado reproduziria em dados a suposição que esta migração existe
para desfazer — e o holerite sairia dizendo "sem incidência de INSS, IRRF e
FGTS" com a autoridade de um dado gravado, não de um chute.

Revision ID: d4a17c60be92
Revises: c3e91b47da28
Create Date: 2026-09-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a17c60be92'
down_revision: Union[str, Sequence[str], None] = 'c3e91b47da28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Idempotente (`sa.inspect` antes de cada `add_column`), no padrão de
    b7d21f9c4a30 e c3e91b47da28: `database.py` chama
    `SQLModel.metadata.create_all` na subida da aplicação, então em deploy as
    colunas novas podem JÁ EXISTIR quando o upgrade roda — e um `add_column`
    cru abortaria o upgrade INTEIRO, deixando a API fora do ar.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas = {c['name'] for c in insp.get_columns('pessoa')}
    if 'vale_alimentacao_forma' not in colunas:
        op.add_column('pessoa', sa.Column('vale_alimentacao_forma', sa.String(), nullable=True))
    if 'vale_alimentacao_natureza_travada_salarial' not in colunas:
        op.add_column('pessoa', sa.Column(
            'vale_alimentacao_natureza_travada_salarial', sa.Boolean(), nullable=True,
        ))


def downgrade() -> None:
    """Downgrade schema.

    Desfaz só o que o upgrade acrescentou. As linhas de holerite já geradas
    (`folha_rubrica` com código `vale_alimentacao`) NÃO são tocadas, e nem
    poderiam ser: o enquadramento delas está CONGELADO na própria linha
    (`natureza`/`incide_inss`/`incide_irrf`/`incide_fgts`, ver
    models/folha_rubrica.py) porque o holerite é prova. Um downgrade de esquema
    apaga a configuração do cadastro; não reescreve documento trabalhista
    emitido — e, sem a coluna, a folha das competências AINDA ABERTAS volta a
    enquadrar como salarial ("forma não informada"), que é o lado que não
    subdeclara base.
    """
    op.drop_column('pessoa', 'vale_alimentacao_natureza_travada_salarial')
    op.drop_column('pessoa', 'vale_alimentacao_forma')
