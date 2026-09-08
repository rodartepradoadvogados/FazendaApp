"""fazenda_id deixa de aceitar nulo nas 152 tabelas que não têm direito a nulo

Etapa aprovada pelo dono como PRÉ-REQUISITO das 130 FKs compostas (ver
docs/security-audit/fks-compostas.md). A ordem foi invertida em relação ao
plano original por um motivo medido: com `fazenda_id` nulo, a FK composta é
INERTE. É o `MATCH SIMPLE` do SQL — se qualquer coluna da chave estrangeira é
nula, a restrição não é verificada. Sem esta migração antes, aquelas 130
constraints seriam trabalho caro que não fecha o que promete.

O QUE ELA FECHA. Hoje o banco aceita um registro nascer sem fazenda, e a
família inteira de problemas da auditoria ("órfão passa por qualquer fazenda")
vive disso: um registro com `fazenda_id` nulo casa com o `if fazenda_id is not
None` tolerante que ainda existe em 676 lugares, e casa com qualquer filtro que
o esqueça. Isto aqui mata na origem — o banco recusa.

AS TABELAS. São 185 com `fazenda_id`; 15 já são NOT NULL; 18 são catálogo
global, onde o NULO é LEGÍTIMO e significa "de todas as fazendas" (ver a lista
`_CATALOGO_GLOBAL` abaixo, e o erro que ela já custou: em 06/09/2026 uma versão
com 14 nomes teria escondido 125 vínculos da Farmácia). Sobram 152.

NUNCA ABORTA O BOOT, e isso é o ponto mais importante deste arquivo.
`database.py::_aplicar_alembic()` roda `upgrade head` no boot da API: uma
migração que levanta exceção não é um erro de migração, é a API fora do ar. Se
alguma tabela ainda tiver linha com `fazenda_id` nulo, ela é PULADA e entra no
relatório — as outras 151 seguem. Melhor 151 travadas e um aviso claro do que
zero travadas e o sistema no chão. E não é só a linha órfã: cada `ALTER` corre
dentro do seu próprio SAVEPOINT, porque no PostgreSQL um comando que falha
aborta a transação inteira — sem ele, um `lock_timeout` numa única tabela levaria
as 152 junto.

SÓ POSTGRESQL. SQLite não tem `ALTER COLUMN ... SET NOT NULL`; alterar coluna
lá exige recriar a tabela (batch mode), e fazer isso com 152 tabelas a cada
execução da suíte seria caro e frágil sem nada em troca — produção é Postgres.
Em SQLite a migração avisa e sai. O efeito real é testado contra um PostgreSQL
de verdade em tests/test_migracao_fazenda_id_not_null.py, no job
`backend-tests-postgres` do CI.

OS MODELOS CONTINUAM `Optional`, de propósito e por ora: são 152 declarações,
e mudá-las é uma frente própria. A consequência está registrada: em banco novo,
o `create_all` cria a coluna aceitando nulo e é esta migração que a fecha logo
em seguida — o estado final é o mesmo, por caminho diferente.

Revision ID: c8e2a4f70b13
Revises: f3c5e07b91aa
Create Date: 2026-09-08 12:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e2a4f70b13"
down_revision: Union[str, Sequence[str], None] = "f3c5e07b91aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# As tabelas em que `fazenda_id` NULO é legítimo: significa "de todas as
# fazendas". Três mecanismos diferentes produzem isso — `rules/visibilidade.py`
# com o `visivel()` explícito, o `_crud_nome_ativo(global_compartilhado=True)`,
# e o copy-on-write por coluna de origem —, e é por isso que a lista não sai de
# uma consulta: ela é conhecimento de domínio, e foi conferida modelo a modelo.
#
# Duas entradas custaram caro para chegar aqui: `medicamento_principio_ativo` e
# `alimento_nutricional` (tabelas de LIGAÇÃO, que espelham o NULO do pai
# global) escaparam da primeira versão desta lista porque não usam `visivel()`.
# Com 14 nomes em vez de 18, a política de RLS teria escondido 125 vínculos da
# Farmácia.
_CATALOGO_GLOBAL: frozenset[str] = frozenset({
    "principio_ativo",
    "doenca",
    "indicacao_terapeutica",
    "medicamento_comercial",
    "categoria_estoque",
    "finalidade_estoque",
    "unidade_estoque",
    "unidade_embalagem_estoque",
    "unidade_medida_embalagem_estoque",
    "laboratorio",
    "categoria_medicamento",
    "classificacao_medicamento_cad",
    "servico_cadastro",
    "parametro_fazenda",
    "medicamento_principio_ativo",
    "alimento_nutricional",
    "medicamento_categoria",
    "medicamento_classificacao",
})


# Tabelas BASE com `fazenda_id`, filtradas por aceitar ou não nulo. VIEW fica de
# fora de propósito — ver a docstring de `_tabelas_alvo`.
_SQL_COLUNAS = (
    "SELECT c.table_name FROM information_schema.columns c "
    "  JOIN information_schema.tables t "
    "    ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
    "WHERE c.table_schema = 'public' AND c.column_name = 'fazenda_id' "
    "  AND c.is_nullable = :nulavel "
    "  AND t.table_type = 'BASE TABLE' "
    "ORDER BY c.table_name"
)


class _Pular(Exception):
    """Motivo para deixar uma tabela como está — não é erro, é decisão."""


def _tabelas_alvo(conn) -> list[str]:
    """Tabelas com `fazenda_id` que aceita nulo e não são catálogo global.

    Sai do catálogo do banco, e não de uma lista escrita à mão, pelo mesmo
    motivo do DDL do RLS: tabela nova com `fazenda_id` entra sozinha na conta,
    em vez de ficar de fora em silêncio até alguém lembrar de acrescentá-la.

    O filtro por `BASE TABLE` não é enfeite: `information_schema.columns` também
    lista VIEWS, e `ALTER TABLE ... SET NOT NULL` numa view levanta exceção — que
    aqui é a API não subir. Hoje não existe view com `fazenda_id`; a consulta é
    escrita para que criar uma amanhã não derrube o boot.
    """
    linhas = conn.execute(sa.text(_SQL_COLUNAS), {"nulavel": "YES"})
    return [linha[0] for linha in linhas if linha[0] not in _CATALOGO_GLOBAL]


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        print(
            "[fazenda_id NOT NULL] dialeto "
            f"{conn.dialect.name!r} — pulado. Alterar coluna fora do PostgreSQL "
            "exigiria recriar cada uma das 152 tabelas; produção é Postgres, e o "
            "efeito é testado contra um Postgres de verdade "
            "(tests/test_migracao_fazenda_id_not_null.py)."
        )
        return

    alvos = _tabelas_alvo(conn)
    aplicadas: list[str] = []
    puladas: dict[str, str] = {}

    for tabela in alvos:
        # Um SAVEPOINT por tabela, envolvendo a contagem TAMBÉM e não só o
        # `ALTER`: no PostgreSQL qualquer comando que falhe aborta a transação
        # inteira, e as duas consultas podem falhar. A contagem cobre uma causa
        # conhecida e dá o número que o operador precisa; o savepoint cobre
        # todas as outras — `lock_timeout` numa tabela em uso, permissão, uma
        # corrida que insira uma órfã entre a contagem e o `ALTER`. Sem ele,
        # uma falha em UMA tabela não pularia uma tabela: levaria as 152 e a
        # API junto.
        marca = conn.begin_nested()
        try:
            orfas = conn.execute(
                sa.text(f'SELECT count(*) FROM "{tabela}" WHERE fazenda_id IS NULL')  # noqa: S608 — nome vem do catálogo do banco
            ).scalar()
            if orfas:
                # Pular é deliberado: `SET NOT NULL` numa tabela com linha nula
                # levanta exceção. A tabela fica como está e aparece no
                # relatório, para virar decisão de gente.
                raise _Pular(f"{orfas} linha(s) com fazenda_id NULL")
            conn.execute(sa.text(f'ALTER TABLE "{tabela}" ALTER COLUMN fazenda_id SET NOT NULL'))
        except _Pular as motivo:
            marca.rollback()
            puladas[tabela] = str(motivo)
            continue
        except sa.exc.SQLAlchemyError as erro:
            marca.rollback()
            puladas[tabela] = f"{type(erro).__name__}: {str(erro.__cause__ or erro).strip()[:200]}"
            continue
        marca.commit()
        aplicadas.append(tabela)

    print(f"[fazenda_id NOT NULL] {len(aplicadas)} tabela(s) travadas, de {len(alvos)} alvo(s).")
    if puladas:
        print(
            f"[fazenda_id NOT NULL] {len(puladas)} PULADA(S) — elas continuam aceitando nulo, "
            "e cada uma precisa de decisão (atribuir as linhas a uma fazenda, apagá-las se "
            "forem resíduo, ou tratar o erro relatado):"
        )
        for tabela, motivo in sorted(puladas.items()):
            print(f"  - {tabela}: {motivo}")
    print(
        f"[fazenda_id NOT NULL] NÃO TOCADAS: as {len(_CATALOGO_GLOBAL)} tabelas de catálogo "
        "global, onde o nulo significa 'de todas as fazendas'."
    )


def downgrade() -> None:
    """Devolve o nulo apenas onde o MODELO diz que a coluna é opcional.

    A distinção importa: 15 tabelas já eram NOT NULL antes desta migração, e um
    downgrade que varresse todas as tabelas com `fazenda_id` afrouxaria também
    aquelas — deixando o banco mais permissivo do que era antes de eu mexer. O
    modelo é a fonte certa para essa pergunta, porque é ele que declara a
    intenção original de cada coluna.
    """
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        print(f"[fazenda_id NOT NULL] downgrade pulado — dialeto {conn.dialect.name!r}.")
        return

    from fazenda.models import SQLModel

    revertidas = 0
    for tabela in _tabelas_nao_nulas_no_banco(conn):
        modelo = SQLModel.metadata.tables.get(tabela)
        coluna = modelo.columns.get("fazenda_id") if modelo is not None else None
        if coluna is None or not coluna.nullable:
            continue  # o modelo quer NOT NULL: não era desta migração
        conn.execute(sa.text(f'ALTER TABLE "{tabela}" ALTER COLUMN fazenda_id DROP NOT NULL'))
        revertidas += 1

    print(f"[fazenda_id NOT NULL] downgrade: {revertidas} tabela(s) voltaram a aceitar nulo.")


def _tabelas_nao_nulas_no_banco(conn) -> list[str]:
    linhas = conn.execute(sa.text(_SQL_COLUNAS), {"nulavel": "NO"})
    return [linha[0] for linha in linhas]
