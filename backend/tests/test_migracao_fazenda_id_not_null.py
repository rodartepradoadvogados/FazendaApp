"""
A migração que tira o nulo de `fazenda_id`, num PostgreSQL de verdade.

Por que não em SQLite: lá não existe `ALTER COLUMN ... SET NOT NULL`, e a
migração sai avisando. O efeito que interessa — o banco passar a RECUSAR
registro sem fazenda — só é observável em Postgres, e é o que este arquivo
mede. Roda no CI, no job `backend-tests-postgres`.

O QUE ESTÁ SENDO PROTEGIDO, em ordem:

1. **A API não pode deixar de subir.** `database.py::_aplicar_alembic()` roda
   `upgrade head` no boot: migração que levanta exceção é a API no chão, não um
   erro de migração. Por isso a tabela que ainda tem linha órfã é PULADA, e não
   aborta o resto. É o teste mais importante daqui.
2. **O nulo some onde não tem direito** — é o objetivo da etapa.
3. **O nulo permanece no catálogo global**, onde significa "de todas as
   fazendas". Travar essas 18 tabelas quebraria a Farmácia, a biblioteca de
   alimentos e o sanitário.
4. **O downgrade não afrouxa o que já era estrito antes.**
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

pytestmark = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (SQLite não altera coluna)",
)

_BANCO = "cowdata_teste_not_null"


def _modulo():
    import importlib.util
    from pathlib import Path

    arquivo = (
        Path(__file__).resolve().parent.parent
        / "alembic" / "versions" / "c8e2a4f70b13_fazenda_id_not_null.py"
    )
    spec = importlib.util.spec_from_file_location("mig_not_null", arquivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Op:
    """`op.get_bind()` fora do Alembic: devolve a conexão do teste."""

    def __init__(self, conn):
        self._conn = conn

    def get_bind(self):
        return self._conn


@pytest.fixture
def banco():
    """Banco descartável com três tabelas que representam os três casos.

    Deliberadamente pequeno: o que se mede aqui é o COMPORTAMENTO da migração
    diante de cada situação, não o esquema real — que muda a cada semana e
    tornaria o teste uma cópia frágil do catálogo.
    """
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        conn.execute(sa.text(f"CREATE DATABASE {_BANCO}"))
    admin.dispose()

    # `render_as_string(hide_password=False)` e não `str()`: `str()` de uma URL
    # do SQLAlchemy troca a senha por `***`, e a conexão sai com asteriscos no
    # lugar dela. Local não dói (autenticação `trust`), no CI é falha de
    # autenticação — foi o que custou um ciclo em test_backup_sob_rls.py.
    engine = sa.create_engine(
        sa.engine.make_url(URL_ADMIN).set(database=_BANCO).render_as_string(hide_password=False)
    )
    with engine.begin() as conn:
        # (1) dado da fazenda, sem órfã: deve virar NOT NULL
        conn.execute(sa.text("CREATE TABLE sanidade (id serial PRIMARY KEY, fazenda_id int, descricao text)"))
        conn.execute(sa.text("INSERT INTO sanidade (fazenda_id, descricao) VALUES (1, 'mastite')"))

        # (2) dado da fazenda COM órfã: deve ser pulada, sem derrubar nada
        conn.execute(sa.text("CREATE TABLE lancamento_item (id serial PRIMARY KEY, fazenda_id int, valor int)"))
        conn.execute(sa.text("INSERT INTO lancamento_item (fazenda_id, valor) VALUES (1, 10), (NULL, 20)"))

        # (3) catálogo global: o nulo é legítimo e tem que continuar aceito
        conn.execute(sa.text("CREATE TABLE principio_ativo (id serial PRIMARY KEY, fazenda_id int, nome text)"))
        conn.execute(sa.text("INSERT INTO principio_ativo (fazenda_id, nome) VALUES (NULL, 'ocitocina')"))

        # (4) já era NOT NULL antes: o downgrade não pode afrouxá-la
        conn.execute(sa.text(
            "CREATE TABLE usuario_fazenda (id serial PRIMARY KEY, fazenda_id int NOT NULL, usuario_id int)"
        ))
        conn.execute(sa.text("INSERT INTO usuario_fazenda (fazenda_id, usuario_id) VALUES (1, 1)"))

    yield engine

    engine.dispose()
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
    admin.dispose()


def _aceita_nulo(conn, tabela: str) -> bool:
    return conn.execute(
        sa.text(
            "SELECT is_nullable = 'YES' FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t AND column_name='fazenda_id'"
        ),
        {"t": tabela},
    ).scalar()


def test_a_tabela_com_orfa_e_pulada_e_a_migracao_nao_levanta(banco):
    """O teste que mais importa: uma tabela com linha órfã não pode derrubar a
    migração, porque a migração roda NO BOOT da API. Derrubá-la é o sistema
    fora do ar, não um erro de migração."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()  # se levantar, o teste falha aqui e é esse o ponto

        assert _aceita_nulo(conn, "lancamento_item"), (
            "a tabela com órfã tinha que ser pulada, e continuar aceitando nulo"
        )
        assert not _aceita_nulo(conn, "sanidade"), (
            "as demais tinham que ser travadas mesmo assim — pular uma não pode parar o resto"
        )


def test_o_banco_passa_a_recusar_registro_sem_fazenda(banco):
    """O objetivo da etapa, medido no comportamento e não no catálogo."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()

    with banco.begin() as conn:
        conn.execute(sa.text("INSERT INTO sanidade (fazenda_id, descricao) VALUES (1, 'ok')"))

    with pytest.raises(sa.exc.IntegrityError):
        with banco.begin() as conn:
            conn.execute(sa.text("INSERT INTO sanidade (fazenda_id, descricao) VALUES (NULL, 'orfa')"))


def test_o_catalogo_global_continua_aceitando_nulo(banco):
    """Travar as 18 de catálogo pararia a Farmácia, a biblioteca de alimentos e
    o sanitário: ali o nulo quer dizer 'de todas as fazendas'."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()
        assert _aceita_nulo(conn, "principio_ativo")

    with banco.begin() as conn:
        conn.execute(sa.text("INSERT INTO principio_ativo (fazenda_id, nome) VALUES (NULL, 'nova global')"))


def test_downgrade_nao_afrouxa_o_que_ja_era_estrito(banco):
    """`usuario_fazenda` já era NOT NULL antes desta migração. Um downgrade que
    varresse todas as tabelas com `fazenda_id` a afrouxaria — deixando o banco
    MAIS permissivo do que era antes de eu mexer."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()
        assert not _aceita_nulo(conn, "sanidade")

        mig.downgrade()

        assert _aceita_nulo(conn, "sanidade"), "o que esta migração travou tinha que ser solto"
        assert not _aceita_nulo(conn, "usuario_fazenda"), (
            "usuario_fazenda já era NOT NULL antes — o downgrade não pode afrouxá-la"
        )


def test_uma_view_com_fazenda_id_nao_derruba_a_migracao(banco):
    """`information_schema.columns` também lista VIEWS, e `ALTER TABLE ... SET
    NOT NULL` numa view levanta exceção — que aqui é a API não subir.

    Hoje o esquema não tem nenhuma view com `fazenda_id`, então este teste não
    prende um defeito existente: ele prende a consulta que filtra por
    `BASE TABLE`, para que criar uma view amanhã não derrube o boot. Sem o
    filtro, este teste fica VERMELHO.
    """
    mig = _modulo()
    with banco.begin() as conn:
        conn.execute(sa.text(
            "CREATE VIEW sanidade_recente AS SELECT id, fazenda_id, descricao FROM sanidade"
        ))

    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()  # sem o filtro, levanta aqui

        assert not _aceita_nulo(conn, "sanidade"), (
            "a view não pode ter impedido as tabelas de verdade de serem travadas"
        )


def test_uma_tabela_travada_por_outra_sessao_nao_leva_as_demais(banco):
    """A contagem de órfãs cobre UMA causa de falha. Esta cobre o resto.

    No PostgreSQL, um comando que levanta erro aborta a transação INTEIRA: sem
    o SAVEPOINT por tabela, uma única falha inesperada não pularia uma tabela —
    levaria as 152 e a API junto, que é exatamente o que este arquivo existe
    para impedir.

    O cenário é o real e não uma simulação: outra sessão está usando uma
    tabela, e a migração roda com `lock_timeout`. O `SHARE MODE` é escolhido de
    propósito — ele conflita com o `ACCESS EXCLUSIVE` que o `ALTER` pede, mas
    não com o `ACCESS SHARE` da contagem. Assim a tabela é contada como limpa e
    falha só no `ALTER`, que é o caso que a contagem não vê.
    """
    mig = _modulo()
    with banco.begin() as conn:
        conn.execute(sa.text("CREATE TABLE ocupada (id serial PRIMARY KEY, fazenda_id int)"))
        conn.execute(sa.text("INSERT INTO ocupada (fazenda_id) VALUES (1)"))

    outra = banco.connect()
    try:
        outra.execute(sa.text("BEGIN"))
        outra.execute(sa.text("LOCK TABLE ocupada IN SHARE MODE"))

        with banco.begin() as conn:
            conn.execute(sa.text("SET LOCAL lock_timeout = '300ms'"))
            mig.op = _Op(conn)
            mig.upgrade()  # sem o SAVEPOINT, levanta aqui e NADA é travado

            assert _aceita_nulo(conn, "ocupada"), (
                "a tabela em uso por outra sessão tinha que ficar como estava"
            )
            assert not _aceita_nulo(conn, "sanidade"), (
                "uma tabela travada por outra sessão não pode impedir as demais"
            )
    finally:
        outra.execute(sa.text("ROLLBACK"))
        outra.close()
