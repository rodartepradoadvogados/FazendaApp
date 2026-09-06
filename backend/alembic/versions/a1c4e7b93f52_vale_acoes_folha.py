"""vale_funcionario/vale_parcela: ações do dono sobre o vale (reparcelar, abater, desconsiderar, cancelar)

O vale aparecia na folha e não dava para mexer nele: a única saída para
qualquer ajuste era editar o vale inteiro (PUT /vales, que recria todas as
parcelas com split igual) ou excluí-lo — e excluir apaga o histórico de um
dinheiro que SAIU de verdade. Faltavam as quatro decisões que o dono toma na
prática, e três delas não cabem em nenhuma coluna existente:

- `vale_funcionario.status` ("ativo" | "cancelado"): cancelar o vale é
  diferente de excluí-lo. O adiantamento continua tendo acontecido; o que
  acaba é a COBRANÇA do funcionário — o saldo pendente vira despesa assumida
  pela fazenda. Sem uma coluna de estado isso viraria exclusão, e o extrato
  perderia a saída de caixa que aconteceu.
- `vale_funcionario.valor_abatido` / `valor_assumido_fazenda`: acumuladores
  do que foi devolvido/perdoado e do que a fazenda assumiu. `valor_total`
  continua sendo o valor efetivamente adiantado (histórico, nunca reescrito
  — mesma regra que `editar_parcela_vale` já seguia), então sem estas duas
  colunas a soma das parcelas divergiria do valor pago sem dizer por quê.
- `vale_parcela.assumida_pela_fazenda` / `motivo_assuncao`: "desconsiderar o
  vale neste mês" não pode apagar a parcela — apagada, o holerite do mês não
  teria como explicar por que o desconto sumiu. A parcela fica, marcada, e
  `_valor_vale` (rh_folha.py) deixa de somá-la.

Todas com default no servidor: as linhas já existentes precisam nascer
"ativo"/0/false, e não há de onde inferir outra coisa.

Revision ID: a1c4e7b93f52
Revises: c3a91f4d20b7
Create Date: 2026-09-06 10:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4e7b93f52'
down_revision: Union[str, Sequence[str], None] = 'c3a91f4d20b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Idempotente (`has_column`), pelo mesmo motivo da migração 4ede0ee68b09:
    `database.py` chama `SQLModel.metadata.create_all` na subida da aplicação.
    Se a app subir antes de o `alembic upgrade head` terminar — o que acontece
    em deploy — as colunas novas já existem e um `add_column` cru aborta o
    upgrade INTEIRO, deixando a API fora do ar.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas_vale = {c['name'] for c in insp.get_columns('vale_funcionario')}
    if 'status' not in colunas_vale:
        op.add_column(
            'vale_funcionario',
            sa.Column('status', sa.String(), nullable=False, server_default='ativo'),
        )
    if 'ix_vale_funcionario_status' not in {
        i['name'] for i in insp.get_indexes('vale_funcionario')
    }:
        op.create_index('ix_vale_funcionario_status', 'vale_funcionario', ['status'])
    if 'valor_abatido' not in colunas_vale:
        op.add_column(
            'vale_funcionario',
            sa.Column('valor_abatido', sa.Float(), nullable=False, server_default='0'),
        )
    if 'valor_assumido_fazenda' not in colunas_vale:
        op.add_column(
            'vale_funcionario',
            sa.Column('valor_assumido_fazenda', sa.Float(), nullable=False, server_default='0'),
        )

    colunas_parcela = {c['name'] for c in insp.get_columns('vale_parcela')}
    if 'assumida_pela_fazenda' not in colunas_parcela:
        op.add_column(
            'vale_parcela',
            sa.Column('assumida_pela_fazenda', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if 'motivo_assuncao' not in colunas_parcela:
        op.add_column('vale_parcela', sa.Column('motivo_assuncao', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('vale_parcela', 'motivo_assuncao')
    op.drop_column('vale_parcela', 'assumida_pela_fazenda')

    op.drop_index('ix_vale_funcionario_status', table_name='vale_funcionario')
    op.drop_column('vale_funcionario', 'valor_assumido_fazenda')
    op.drop_column('vale_funcionario', 'valor_abatido')
    op.drop_column('vale_funcionario', 'status')
