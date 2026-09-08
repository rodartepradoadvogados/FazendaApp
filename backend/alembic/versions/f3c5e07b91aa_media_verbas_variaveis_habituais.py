"""ferias/13o/rescisao: media das verbas variaveis habituais e sua composicao

O QUE ESTA MIGRAÇÃO ABRE. Até aqui, `calcular_ferias`,
`calcular_decimo_terceiro` e `calcular_rescisao` (fazenda/rules/folha_rh.py)
recebiam UM número — `Pessoa.salario_base` — e não consultavam rubrica
nenhuma. Nenhuma parcela salarial VARIÁVEL habitual entrava nas bases de 13º,
férias e rescisão: nem bonificação por produtividade, nem gueltas, nem
vale-alimentação de natureza salarial, nem insalubridade. Era subdeclaração de
todo funcionário com remuneração variável (CLT, art. 457, §1º; Súmula 45 do
TST), e estava registrada como `LIMITE CONHECIDO` na docstring de
`rules/vale_alimentacao.py`.

Agora a média entra — quando a fazenda LIGAR o parâmetro
`calcula_media_verbas_variaveis` (grupo `folha_rh`, padrão FALSO). Estas
colunas são a FOTOGRAFIA do que entrou:

`ferias_funcionario` e `decimo_terceiro`
  - `media_variaveis`             — a média mensal aplicada (float);
  - `media_variaveis_composicao`  — o JSON que permite conferi-la: as
    competências que entraram, as rubricas de cada uma, o total, o divisor e
    o critério do divisor.

`rescisao_funcionario`
  - `media_variaveis_decimo_terceiro`, `media_variaveis_ferias`,
    `media_variaveis_aviso_previo` — TRÊS, porque na rescisão cada verba segue
    a regra da sua natureza: o 13º proporcional pela média do ANO CIVIL
    (Decreto 57.155/65, art. 2º), as férias vencidas e proporcionais pela do
    PERÍODO AQUISITIVO (CLT, art. 142, §§ 1º a 6º) e o aviso prévio
    indenizado pela dos ÚLTIMOS 12 MESES. Uma coluna só gravaria a resposta
    errada para duas das três verbas;
  - `media_variaveis_composicao`  — as três composições num JSON.

POR QUE SNAPSHOT, E NÃO CÁLCULO NA LEITURA. Mesmo motivo de
`FeriasFuncionario.salario_base`, de `RescisaoFuncionario.salario_base` e de
`FolhaPagamento.discriminacao_congelada`: o recibo é PROVA. Uma folha lançada
depois, ou uma rubrica corrigida numa competência ainda aberta, mudaria o
valor de umas férias já lançadas se a média fosse recalculada a cada leitura.

POR QUE NULLABLE E SEM `server_default`. A migração roda no BOOT da API
(`database.py::_aplicar_alembic`), e um `server_default` num
`ALTER TABLE ADD COLUMN` obriga o Postgres a reescrever a tabela inteira antes
de a API subir. E NULL é a informação CERTA para o passado: significa "a média
não foi apurada neste lançamento" — que é diferente de `0.0`, "foi apurada e
deu zero". O recibo mostra uma coisa ou outra, e não pode confundir as duas.

NENHUM BACKFILL, e a ausência é decisão. Recalcular a média dos lançamentos
antigos reescreveria — em cima de férias, 13º e rescisões JÁ PAGOS — um valor
que ninguém pagou. Dinheiro que já saiu não muda de número retroativamente
porque uma feature nova entrou. Os registros antigos ficam com NULL, o recibo
deles continua exatamente o que sempre foi, e a média vale do próximo
lançamento em diante — e só na fazenda que ligar o parâmetro.

Revision ID: f3c5e07b91aa
Revises: d4a17c60be92
Create Date: 2026-09-08 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c5e07b91aa'
down_revision: Union[str, Sequence[str], None] = 'd4a17c60be92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabela, coluna, tipo) — a lista é dado, não código repetido três vezes.
COLUNAS: list[tuple[str, str, sa.types.TypeEngine]] = [
    ('ferias_funcionario', 'media_variaveis', sa.Float()),
    ('ferias_funcionario', 'media_variaveis_composicao', sa.String()),
    ('decimo_terceiro', 'media_variaveis', sa.Float()),
    ('decimo_terceiro', 'media_variaveis_composicao', sa.String()),
    ('rescisao_funcionario', 'media_variaveis_decimo_terceiro', sa.Float()),
    ('rescisao_funcionario', 'media_variaveis_ferias', sa.Float()),
    ('rescisao_funcionario', 'media_variaveis_aviso_previo', sa.Float()),
    ('rescisao_funcionario', 'media_variaveis_composicao', sa.String()),
]


def upgrade() -> None:
    """Upgrade schema.

    Idempotente (`sa.inspect` antes de cada `add_column`), no padrão de
    d4a17c60be92, c3e91b47da28 e b7d21f9c4a30: `database.py` chama
    `SQLModel.metadata.create_all` na subida da aplicação, então em deploy as
    colunas novas podem JÁ EXISTIR quando o upgrade roda — e um `add_column`
    cru abortaria o upgrade INTEIRO, deixando a API fora do ar (e a CI com
    duas cabeças).
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    for tabela, coluna, tipo in COLUNAS:
        if tabela not in insp.get_table_names():
            # Banco sem a tabela ainda (ordem de criação em ambiente novo):
            # `create_all` já vai criar a coluna junto. Nada a fazer aqui.
            continue
        existentes = {c['name'] for c in insp.get_columns(tabela)}
        if coluna not in existentes:
            op.add_column(tabela, sa.Column(coluna, tipo, nullable=True))


def downgrade() -> None:
    """Downgrade schema.

    Desfaz só o que o upgrade acrescentou. Os valores de férias, 13º e
    rescisão JÁ GRAVADOS não são tocados: eles estão em
    `valor_total`/`valor_integral`/`valor_bruto`, que são colunas próprias e
    continuam sendo o que foi lançado. O que se perde no downgrade é a
    CONFERÊNCIA (a composição da média), não o dinheiro — e é por isso que ele
    é seguro apesar de destrutivo: nenhum recibo muda de valor.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    for tabela, coluna, _tipo in reversed(COLUNAS):
        if tabela not in insp.get_table_names():
            continue
        existentes = {c['name'] for c in insp.get_columns(tabela)}
        if coluna in existentes:
            op.drop_column(tabela, coluna)
