"""fazenda.eh_teste — marca fazenda de demonstração/sandbox em produção

Mesmo padrão de `Fazenda.eh_empresa_cowdata` (ver fazenda/models/multitenant.py):
mais uma flag booleana simples na tabela `fazenda`, default False. Serve pra
três coisas (decisão do dono do produto, 04/09/2026):

  a) marcar fazendas de demonstração/sandbox que vivem no MESMO banco de
     produção (ex.: a "Fazenda Teste", id=2 hoje);
  b) ser a TRAVA DURA da rotina de replicação da fazenda #1 — outra frente
     do retrofit só pode GRAVAR em fazenda com eh_teste=True, nunca em
     fazenda de cliente de verdade;
  c) excluir essas fazendas de cobrança/métricas/alertas no futuro (ainda
     não implementado — só a coluna e o dado, por enquanto).

Dado: marca `eh_teste=True` só na fazenda cujo nome é EXATAMENTE "Fazenda
Teste" — nunca por id (não custa nada supor que o id=2 de hoje é sempre a
mesma fazenda em todo ambiente; o nome é o identificador estável que o
dono do produto já usa pra se referir a ela). Se não achar nenhuma fazenda
com esse nome exato (ambiente de teste automatizado, ou produção antes de
existir essa fazenda), não cria nada — só avisa no relatório. Se achar MAIS
de uma (duas fazendas de teste com o mesmo nome, por acaso), marca todas —
não é ambíguo pra este caso: "eh_teste" nunca teve custo de estar errado
"a mais" (só desliga cobrança/replicação-alvo), ao contrário do backfill de
fazenda_id de dado real.

Revision ID: 089c4e98da6d
Revises: c24befa94c1b
Create Date: 2026-09-05 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '089c4e98da6d'
down_revision: Union[str, Sequence[str], None] = 'c24befa94c1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOME_FAZENDA_TESTE = 'Fazenda Teste'


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    colunas = {c['name'] for c in insp.get_columns('fazenda')}
    if 'eh_teste' not in colunas:
        op.add_column('fazenda', sa.Column('eh_teste', sa.Boolean(), nullable=False, server_default=sa.false()))

    afetadas = conn.execute(sa.text(
        "UPDATE fazenda SET eh_teste = TRUE WHERE nome = :nome"
    ), {"nome": NOME_FAZENDA_TESTE}).rowcount or 0

    if afetadas:
        print(f"[fazenda.eh_teste] marcada(s) {afetadas} fazenda(s) com nome exato "
              f"'{NOME_FAZENDA_TESTE}' como eh_teste=True.")
    else:
        print(f"[fazenda.eh_teste] nenhuma fazenda com nome exato '{NOME_FAZENDA_TESTE}' encontrada — "
              "nenhuma linha marcada (revisar manualmente se esperava encontrar uma).")


def downgrade() -> None:
    with op.batch_alter_table('fazenda', schema=None) as batch_op:
        batch_op.drop_column('eh_teste')
