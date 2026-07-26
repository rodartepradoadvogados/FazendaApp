"""RH/Folha de pagamento: fazenda_id (Fase 4B)

Fecha o maior gap restante do retrofit multi-tenant — o domínio de RH/Folha
de pagamento (Empreitada, Contrato, Diária, FolhaPagamento, Férias, 13º,
Vale de funcionário/avulso, TipoPessoa) nunca teve `fazenda_id`. Mesma
coluna aditiva (nullable, com índice) já usada em todo o resto do sistema,
backfillada para a fazenda #1 (grandfathered) quando ela já existir — sem
retroatividade em nenhuma outra fazenda.

tipo_pessoa.nome tinha unique global — vira unique(nome, fazenda_id), mesmo
padrão de tipo_servico_reprodutivo (c1d2e3f4a5b6), senão a 2ª fazenda nunca
conseguiria cadastrar um tipo com o mesmo nome já usado (ex.: "Empreiteiro").

parametro_diaria_padrao era uma linha única (id=1, mesmo padrão de
AlimentacaoEstado) — vira uma linha por fazenda, com unique(fazenda_id)
sozinho (não um par campo+fazenda_id como as demais, pois a própria linha é
a config "singleton" da fazenda).

vale_avulso_abatimento não recebe fazenda_id — é sempre acessado através de
`vale_avulso_id` (que já é escopado), sem nenhum endpoint de listagem
direta.

`diaria_auditoria` e `parametro_diaria_padrao` nunca tiveram uma migração de
criação própria (nasceram depois da adoção do Alembic e são cobertas pela
rede de segurança `SQLModel.metadata.create_all` em
`database.py::create_db_and_tables`, chamada logo após o `upgrade head`) —
em um banco totalmente novo (sem nenhuma tabela ainda) elas simplesmente não
existem no momento em que esta migração roda, e o `ALTER TABLE` falharia.
Por isso o upgrade só altera essas duas tabelas SE elas já existirem —
quando não existirem, `create_all` as cria do zero já com `fazenda_id`
(presente no modelo). Em produção (banco pré-existente, ambas já criadas
por um `create_all` anterior) o `ALTER TABLE` roda normalmente.

Revision ID: a1b2c3d4e5f6
Revises: c1d2e3f4a5b6
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelas simples — só ganham a coluna aditiva (sem conflito de unicidade).
_TABELAS = [
    'folha_pagamento',
    'ferias_funcionario',
    'decimo_terceiro',
    'vale_funcionario',
    'vale_parcela',
    'vale_avulso',
    'empreitada',
    'empreitada_parcela',
    'empreitada_etapa',
    'contrato',
    'contrato_parcela',
    'diaria',
    'diaria_pagamento',
    'diaria_auditoria',
]

# (tabela, coluna do campo único, nome da constraint nova) — nome+fazenda_id.
_TABELAS_CAMPO_UNICO = [
    ('tipo_pessoa', 'nome', 'uq_tipo_pessoa_nome_fazenda'),
]

# parametro_diaria_padrao: unique(fazenda_id) sozinho — tratado à parte.
_TABELA_SINGLETON = 'parametro_diaria_padrao'
_SINGLETON_CONSTRAINT = 'uq_parametro_diaria_padrao_fazenda'

# Tabelas sem migração de criação própria — só existem se um `create_all`
# anterior já as tiver criado (ver nota acima). Em banco totalmente novo,
# ainda não existem neste ponto da cadeia de migrações.
_TABELAS_SEM_MIGRACAO_DE_CRIACAO = {'diaria_auditoria', _TABELA_SINGLETON}


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)
    fazenda_1_existe = conn.execute(sa.text("SELECT id FROM fazenda WHERE id = 1")).first()

    for tabela in _TABELAS:
        if tabela in _TABELAS_SEM_MIGRACAO_DE_CRIACAO and not insp.has_table(tabela):
            continue
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))

    for tabela, campo, nome_constraint in _TABELAS_CAMPO_UNICO:
        op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {tabela} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            try:
                batch_op.drop_index(f'ix_{tabela}_{campo}')
            except Exception:
                pass
            batch_op.create_index(f'ix_{tabela}_{campo}', [campo], unique=False)
            batch_op.create_unique_constraint(nome_constraint, [campo, 'fazenda_id'])

    if insp.has_table(_TABELA_SINGLETON):
        op.add_column(_TABELA_SINGLETON, sa.Column('fazenda_id', sa.Integer(), nullable=True))
        op.create_index(op.f(f'ix_{_TABELA_SINGLETON}_fazenda_id'), _TABELA_SINGLETON, ['fazenda_id'], unique=False)
        if fazenda_1_existe:
            conn.execute(sa.text(f"UPDATE {_TABELA_SINGLETON} SET fazenda_id = 1 WHERE fazenda_id IS NULL"))
        with op.batch_alter_table(_TABELA_SINGLETON, schema=None) as batch_op:
            batch_op.create_unique_constraint(_SINGLETON_CONSTRAINT, ['fazenda_id'])


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if insp.has_table(_TABELA_SINGLETON) and _SINGLETON_CONSTRAINT in {
        c['name'] for c in insp.get_unique_constraints(_TABELA_SINGLETON)
    }:
        with op.batch_alter_table(_TABELA_SINGLETON, schema=None) as batch_op:
            batch_op.drop_constraint(_SINGLETON_CONSTRAINT, type_='unique')
        op.drop_index(op.f(f'ix_{_TABELA_SINGLETON}_fazenda_id'), table_name=_TABELA_SINGLETON)
        op.drop_column(_TABELA_SINGLETON, 'fazenda_id')

    for tabela, campo, nome_constraint in reversed(_TABELAS_CAMPO_UNICO):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_constraint(nome_constraint, type_='unique')
            batch_op.drop_index(f'ix_{tabela}_{campo}')
            batch_op.create_index(f'ix_{tabela}_{campo}', [campo], unique=True)
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')

    for tabela in reversed(_TABELAS):
        if tabela in _TABELAS_SEM_MIGRACAO_DE_CRIACAO and not insp.has_table(tabela):
            continue
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
