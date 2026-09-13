"""consumo de alimento por lote, sobra do cocho e permissões do lote

Cria o lançamento de consumo diário — o que foi REALMENTE fornecido a cada
lote, por alimento — e a sobra do cocho. É o que faltava para a alimentação
lançada pelo app afetar o estoque: a baixa automática de hoje lê a tabela
LEGADA `dieta` (a do CSV do Ideagri), não a `dieta_lancamento` que a tela usa,
então nada do que se lança hoje debita nada.

Duas tabelas, com regras de acumulação DIFERENTES e deliberadas:

  consumo_alimento  SOMA no mesmo dia. O trato é fracionado — cada passada do
                    vagão é um lançamento, e o total do dia é a soma deles.
  consumo_sobra     SUBSTITUI no mesmo dia. Sobra é uma medição única do dia,
                    não um acúmulo de eventos; lançar de novo é corrigir o que
                    se mediu antes, não acrescentar. A UniqueConstraint por
                    (fazenda, lote, data) trava isso no banco, para não depender
                    de a aplicação lembrar da regra.

A sobra é gravada em QUILOS TOTAIS do lote, nunca por alimento: ninguém separa
o que sobrou no cocho por ingrediente. O rateio por alimento é calculado a
partir da proporção da dieta e nunca persistido — persistir o rateio o
congelaria, e ele muda quando a dieta muda.

`lote` é INT nas duas tabelas, a mesma representação de `dieta_lancamento.lote`,
porque o lançamento de consumo só existe ancorado numa dieta ativa e tem de
falar a língua dela. O sistema tem quatro representações de lote convivendo
(código de 2 dígitos em `lote.codigo`, string composta em
`animal.grupo_primario`, este int, e string livre em Recria/Sanidade) — a ponte
para o cadastro é `f"{lote:02d}"`, como já faz a apresentação de dieta.

As duas colunas novas em `lote` nascem FALSE: cada uma desliga uma checagem que
existe para pegar erro de digitação no curral, e o padrão restritivo é o seguro.

Tudo aditivo: nenhum registro existente muda de comportamento.

Revision ID: b7c04e91d2af
Revises: fd30a36c88cf
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b7c04e91d2af'
down_revision: Union[str, Sequence[str], None] = 'fd30a36c88cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Idempotente por tabela e por coluna (`insp.has_table` / `has_column`),
    como as demais migrações que criam tabela neste repositório. Não é
    preciosismo: a subida da aplicação chama `create_all` como rede de
    segurança, então um banco de dev ou de teste pode já ter as tabelas
    quando o Alembic chega — e sem a guarda a migração estoura com "table
    already exists". Há teste travando exatamente isso.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('consumo_alimento'):
        op.create_table(
            'consumo_alimento',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('data', sa.Date(), nullable=False),
            sa.Column('lote', sa.Integer(), nullable=False),
            sa.Column('alimento', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('alimento_id', sa.Integer(), nullable=True),
            sa.Column('quantidade', sa.Float(), nullable=False),
            sa.Column('unidade', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('num_animais', sa.Integer(), nullable=True),
            sa.Column('origem', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('fora_da_dieta', sa.Boolean(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['alimento_id'], ['alimento.id'], ),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_consumo_alimento_fazenda_id'), 'consumo_alimento', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_consumo_alimento_data'), 'consumo_alimento', ['data'], unique=False)
        op.create_index(op.f('ix_consumo_alimento_lote'), 'consumo_alimento', ['lote'], unique=False)

    if not insp.has_table('consumo_sobra'):
        op.create_table(
            'consumo_sobra',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('fazenda_id', sa.Integer(), nullable=True),
            sa.Column('data', sa.Date(), nullable=False),
            sa.Column('lote', sa.Integer(), nullable=False),
            sa.Column('kg_sobra', sa.Float(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('criado_em', sa.DateTime(), nullable=False),
            sa.Column('atualizado_em', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['fazenda_id'], ['fazenda.id'], ),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('fazenda_id', 'lote', 'data', name='uq_consumo_sobra_fazenda_lote_data'),
        )
        op.create_index(op.f('ix_consumo_sobra_fazenda_id'), 'consumo_sobra', ['fazenda_id'], unique=False)
        op.create_index(op.f('ix_consumo_sobra_data'), 'consumo_sobra', ['data'], unique=False)
        op.create_index(op.f('ix_consumo_sobra_lote'), 'consumo_sobra', ['lote'], unique=False)

    # server_default garante que as linhas JÁ EXISTENTES de `lote` recebam o
    # valor restritivo; sem ele o NOT NULL falharia num banco com dados.
    colunas_lote = {c['name'] for c in insp.get_columns('lote')} if insp.has_table('lote') else set()
    novas = [c for c in ('permitir_fora_da_dieta', 'permitir_sem_estoque') if c not in colunas_lote]
    if novas:
        with op.batch_alter_table('lote', schema=None) as batch_op:
            for nome in novas:
                batch_op.add_column(sa.Column(nome, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    colunas_lote = {c['name'] for c in insp.get_columns('lote')} if insp.has_table('lote') else set()
    remover = [c for c in ('permitir_sem_estoque', 'permitir_fora_da_dieta') if c in colunas_lote]
    if remover:
        with op.batch_alter_table('lote', schema=None) as batch_op:
            for nome in remover:
                batch_op.drop_column(nome)

    if insp.has_table('consumo_sobra'):
        op.drop_index(op.f('ix_consumo_sobra_lote'), table_name='consumo_sobra')
        op.drop_index(op.f('ix_consumo_sobra_data'), table_name='consumo_sobra')
        op.drop_index(op.f('ix_consumo_sobra_fazenda_id'), table_name='consumo_sobra')
        op.drop_table('consumo_sobra')

    if insp.has_table('consumo_alimento'):
        op.drop_index(op.f('ix_consumo_alimento_lote'), table_name='consumo_alimento')
        op.drop_index(op.f('ix_consumo_alimento_data'), table_name='consumo_alimento')
        op.drop_index(op.f('ix_consumo_alimento_fazenda_id'), table_name='consumo_alimento')
        op.drop_table('consumo_alimento')
