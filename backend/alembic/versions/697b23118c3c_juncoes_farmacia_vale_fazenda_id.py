"""fazenda_id nas 6 tabelas de junção de Farmácia/Vale avulso

Estas seis tabelas de junção pertencem de fato a dado de FAZENDA (via FK a
`estoque`/`vale_avulso`), mas nunca ganharam coluna `fazenda_id` própria:
`estoque_principio_ativo`, `medicamento_categoria`, `medicamento_classificacao`,
`estoque_categoria_medicamento`, `estoque_classificacao_medicamento`,
`vale_avulso_abatimento`.

Consequência prática (o motivo real desta migração): o motor de replicação
Fazenda -> Fazenda (fazenda/rules/replicacao_fazenda.py, ver "Motor de
replicação Fazenda -> Fazenda (sandbox de testes)") descobre DINAMICAMENTE o
que copiar procurando, no metadata do SQLModel, toda tabela que tem coluna
`fazenda_id` — essas seis, sem a coluna, ficavam de fora da varredura e nunca
eram copiadas. Resultado: sincronizar a Fazenda Teste copiava o item de
estoque, mas ele chegava lá SEM princípio ativo, SEM categoria(s) e SEM
classificação(ões) — e o vale avulso chegava sem o abatimento já aplicado
nele. Diferença silenciosa entre sandbox e produção é exatamente o que um
sandbox de testes não pode ter (o propósito dele é ser fiel à produção).

Backfill: deriva o `fazenda_id` do PAI de cada linha (a fonte mais confiável,
mesmo critério de 029227481e9e), nunca de "fazenda única" — encadear direto
por FK não deixa ambiguidade nenhuma, mesmo com várias fazendas reais:

  - estoque_principio_ativo.fazenda_id            <- estoque.fazenda_id (via estoque_id)
  - estoque_categoria_medicamento.fazenda_id       <- estoque.fazenda_id (via estoque_id)
  - estoque_classificacao_medicamento.fazenda_id   <- estoque.fazenda_id (via estoque_id)
  - vale_avulso_abatimento.fazenda_id              <- vale_avulso.fazenda_id (via vale_avulso_id)
  - medicamento_categoria.fazenda_id               <- medicamento_comercial.fazenda_id (via medicamento_comercial_id)
  - medicamento_classificacao.fazenda_id           <- medicamento_comercial.fazenda_id (via medicamento_comercial_id)

As duas últimas merecem atenção à parte: `medicamento_comercial` é CATÁLOGO
(ver fazenda/rules/visibilidade.py) — pode ser GLOBAL (`fazenda_id` nulo,
catálogo do dono do SaaS, semeado igual para todo produtor) ou já
"personalizado" por uma fazenda específica. O vínculo de categoria/
classificação de um medicamento GLOBAL tem que CONTINUAR global (nulo) —
gravar aqui a fazenda de quem só o está CONSULTANDO estaria errado (faria o
vínculo "sumir" do catálogo global de todas as outras fazendas) e não é o
que este backfill faz: ele deriva do PRÓPRIO `medicamento_comercial.
fazenda_id` da linha, então um medicamento global gera vínculo global (nulo
continua nulo) e um medicamento já vinculado a uma fazenda gera vínculo
daquela mesma fazenda. Nenhuma linha de `medicamento_categoria`/
`medicamento_classificacao` fica "adivinhada".

Revision ID: 697b23118c3c
Revises: 089c4e98da6d
Create Date: 2026-09-05 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '697b23118c3c'
down_revision: Union[str, Sequence[str], None] = '089c4e98da6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabela, coluna_fk_do_pai, tabela_pai) — todas derivam do pai; nenhuma tem
# fallback de "fazenda única": encadear pela FK já resolve sem ambiguidade.
_TABELAS: list[tuple[str, str, str]] = [
    ('estoque_principio_ativo', 'estoque_id', 'estoque'),
    ('estoque_categoria_medicamento', 'estoque_id', 'estoque'),
    ('estoque_classificacao_medicamento', 'estoque_id', 'estoque'),
    ('vale_avulso_abatimento', 'vale_avulso_id', 'vale_avulso'),
    ('medicamento_categoria', 'medicamento_comercial_id', 'medicamento_comercial'),
    ('medicamento_classificacao', 'medicamento_comercial_id', 'medicamento_comercial'),
]


def _derivar_do_pai(conn, tabela: str, coluna_fk: str, tabela_pai: str) -> int:
    """Mesma estratégia (a) de 029227481e9e — deriva via subquery em vez de
    UPDATE...FROM para funcionar igual em SQLite (testes) e Postgres
    (produção). Só atualiza quando o pai tem `fazenda_id` preenchido (deixa
    nulo, sem adivinhar, quando o pai também está nulo — ex.: medicamento
    global)."""
    resultado = conn.execute(sa.text(
        f"UPDATE {tabela} SET fazenda_id = ("
        f"  SELECT p.fazenda_id FROM {tabela_pai} p WHERE p.id = {tabela}.{coluna_fk}"
        f") WHERE fazenda_id IS NULL AND {coluna_fk} IS NOT NULL AND EXISTS ("
        f"  SELECT 1 FROM {tabela_pai} p WHERE p.id = {tabela}.{coluna_fk} AND p.fazenda_id IS NOT NULL"
        f")"
    ))
    return resultado.rowcount or 0


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tabelas_existentes = set(insp.get_table_names())

    por_pai: dict[str, int] = {}
    for tabela, coluna_fk, tabela_pai in _TABELAS:
        # A tabela pode não existir ainda (banco parcial) e a coluna pode já
        # existir (banco criado pelo metadata dos modelos, sem passar por
        # migração — cenário real neste projeto, ver
        # 4ede0ee68b09_cria_tabelas_sem_migracao e o teste-sentinela
        # test_migracao_e_idempotente_em_banco_que_ja_tem_as_tabelas). Sem
        # estas duas guardas o `alembic upgrade head` morre com "duplicate
        # column name". Mesmo padrão de 6aec9b930e1a.
        if tabela not in tabelas_existentes:
            continue
        colunas = {c['name'] for c in insp.get_columns(tabela)}
        if 'fazenda_id' not in colunas:
            # Coluna aditiva (nullable, com índice) — mesmo padrão já usado em
            # dezenas de migrações do retrofit multi-tenant (ver f7a8b9c0d1e2,
            # f4a5b6c7d8e9, etc.). Sem constraint UNIQUE nova: nenhuma destas
            # tabelas precisa disso (o vínculo em si já é único por
            # (dono, tag) na constraint existente, sem fazenda_id).
            op.add_column(tabela, sa.Column('fazenda_id', sa.Integer(), nullable=True))
            op.create_index(op.f(f'ix_{tabela}_fazenda_id'), tabela, ['fazenda_id'], unique=False)

        if tabela_pai in tabelas_existentes:
            por_pai[tabela] = _derivar_do_pai(conn, tabela, coluna_fk, tabela_pai)

    total = sum(por_pai.values())
    print(f"[juncoes_farmacia_vale fazenda_id] preenchidas via PAI: {total} linha(s)")
    for tabela, n in por_pai.items():
        print(f"  - {tabela}: {n} linha(s)")
    # Linhas cujo pai também tem fazenda_id nulo (ex.: medicamento GLOBAL)
    # ficam nulas de propósito — não é pendência, é o comportamento correto
    # (ver docstring desta migração). Só reporta o que sobrou nulo COM pai
    # preenchido, que sinalizaria um bug na derivação (não deveria acontecer).
    for tabela, coluna_fk, tabela_pai in _TABELAS:
        if tabela not in tabelas_existentes or tabela_pai not in tabelas_existentes:
            continue
        pendente = conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {tabela} t JOIN {tabela_pai} p ON p.id = t.{coluna_fk} "
            f"WHERE t.fazenda_id IS NULL AND p.fazenda_id IS NOT NULL"
        )).scalar() or 0
        if pendente:
            print(f"[juncoes_farmacia_vale fazenda_id] AVISO: {tabela} ainda tem {pendente} linha(s) "
                  "com pai preenchido e fazenda_id nulo — investigar.")


def downgrade() -> None:
    for tabela, _coluna_fk, _tabela_pai in reversed(_TABELAS):
        op.drop_index(op.f(f'ix_{tabela}_fazenda_id'), table_name=tabela)
        op.drop_column(tabela, 'fazenda_id')
