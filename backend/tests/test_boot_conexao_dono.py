"""
O boot da API sob RLS: migrações e seeds precisam da conexão de DONO.

O QUE ESTE ARQUIVO IMPEDE. O roteiro do RLS
(docs/security-audit/railway-staging-passos.md) cria um role de aplicação
(`cowdata_app`) com SELECT/INSERT/UPDATE/DELETE e NADA MAIS — de propósito: é
não ser dono das tabelas que faz a política valer para ele. Mas
`main.py::lifespan` chama `create_db_and_tables()` ANTES de servir a primeira
requisição, e lá dentro `_aplicar_alembic()` roda `upgrade head` sem nenhuma
proteção em volta.

Com a conexão contida, a primeira migração que criasse ou alterasse uma tabela
seria recusada pelo banco e a API NÃO SUBIRIA. Não é hipótese: o Staging já
está rodando com o `cowdata_app` desde 08/09/2026, e a migração das 130 FKs
compostas altera dezenas de tabelas.

Os dois testes abaixo são um par, e é o par que dá sentido a cada um:

  1. com a conexão de dono, o boot completa;
  2. sem ela — a conexão contida nas duas pontas —, o mesmo boot é recusado
     com `permission denied`. É o teste 2 que prova que o teste 1 mede alguma
     coisa; sem ele, o primeiro passaria mesmo se a correção fosse revertida.

Roda só em PostgreSQL: SQLite não tem role, GRANT nem dono de tabela — o
cenário inteiro não existe lá.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

import pytest
import sqlalchemy as sa

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

pytestmark = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (SQLite não tem role)",
)

_BANCO = "cowdata_teste_boot_dono"
_SENHA = "teste_boot_local"


def _url(usuario: str, banco: str) -> str:
    # `render_as_string(hide_password=False)` e não `str()`: `str()` mascara a
    # senha como `***` e a conexão sai com asteriscos (ver test_backup_sob_rls).
    return (
        sa.engine.make_url(URL_ADMIN)
        .set(database=banco, username=usuario, password=_SENHA)
        .render_as_string(hide_password=False)
    )


@pytest.fixture
def papeis():
    """Reproduz o Staging: um role DONO e um role de aplicação contido.

    Os GRANTs são exatamente os do roteiro — nem mais (o que tornaria o teste
    otimista) nem menos.
    """
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        for papel in ("dono_teste_boot", "app_teste_boot"):
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {papel}"))
            conn.execute(sa.text(f"CREATE ROLE {papel} LOGIN PASSWORD '{_SENHA}'"))
        conn.execute(sa.text(f"CREATE DATABASE {_BANCO} OWNER dono_teste_boot"))
    admin.dispose()

    dono = sa.create_engine(_url("dono_teste_boot", _BANCO), isolation_level="AUTOCOMMIT")
    with dono.connect() as conn:
        conn.execute(sa.text(f"GRANT CONNECT ON DATABASE {_BANCO} TO app_teste_boot"))
        conn.execute(sa.text("GRANT USAGE ON SCHEMA public TO app_teste_boot"))
        conn.execute(sa.text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_teste_boot"
        ))
    dono.dispose()

    yield

    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        for papel in ("app_teste_boot", "dono_teste_boot"):
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {papel}"))
    admin.dispose()


def _montar(monkeypatch, *, manutencao_e_dono: bool):
    """Aponta o módulo `database` para os dois roles e devolve as engines.

    Sem recarregar o módulo de propósito: `engine`/`engine_manutencao` são
    globais lidas pelas funções em tempo de chamada, então trocá-las é
    suficiente — e um `importlib.reload` deixaria o resto da suíte com
    referências a um módulo diferente do que ela importou.
    """
    import fazenda.database as database

    url_app = _url("app_teste_boot", _BANCO)
    url_dono = _url("dono_teste_boot", _BANCO)
    eng_app = sa.create_engine(url_app)
    eng_manut = sa.create_engine(url_dono if manutencao_e_dono else url_app)

    monkeypatch.setattr(database, "engine", eng_app)
    monkeypatch.setattr(database, "engine_manutencao", eng_manut)
    monkeypatch.setattr(
        database, "DATABASE_URL_MANUTENCAO", url_dono if manutencao_e_dono else url_app
    )
    return database, eng_app, eng_manut


def test_com_a_conexao_de_dono_o_boot_completa(monkeypatch, papeis):
    """O que a correção de 09/09/2026 garante."""
    database, eng_app, eng_manut = _montar(monkeypatch, manutencao_e_dono=True)
    try:
        database.create_db_and_tables()  # se levantar, a API não subiria

        with eng_manut.connect() as conn:
            n = conn.execute(sa.text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )).scalar()
        assert n > 100, f"o schema tinha que ter sido criado pelo dono (achei {n} tabelas)"

        # E a aplicação contida enxerga o que o dono criou — é para isso que
        # servem os ALTER DEFAULT PRIVILEGES do roteiro.
        with eng_app.connect() as conn:
            conn.execute(sa.text("SELECT count(*) FROM fazenda"))
    finally:
        eng_app.dispose()
        eng_manut.dispose()


def test_alembic_usa_a_conexao_de_dono_nao_a_da_aplicacao(monkeypatch, papeis):
    """Regressão do bug de 10/09/2026: `alembic/env.py` importava e usava
    `DATABASE_URL` (o role de aplicação) em vez de `DATABASE_URL_MANUTENCAO`
    (o role dono) — e como `config` dentro de `env.py` é o MESMO objeto que
    `_aplicar_alembic()` monta com a URL de dono, essa linha SOBRESCREVIA a
    URL certa assim que `command.upgrade` carregava `env.py`. Toda migração
    de verdade (a que só existe no Staging, com `cowdata_app` restrito)
    passava a tentar rodar pela conexão ERRADA — "must be owner of table X".

    O teste acima (`test_com_a_conexao_de_dono_o_boot_completa`) NÃO pega
    isso: ele nunca diferencia `DATABASE_URL` de `DATABASE_URL_MANUTENCAO`
    (só a segunda é trocada), e mesmo quando o bug redireciona `env.py` para
    outro banco (SQLite, no ambiente de teste — `DATABASE_URL` nunca foi
    trocada ali), `create_all(engine_manutencao)` cria as tabelas de qualquer
    jeito, como rede de segurança, mascarando que o Alembic em si rodou no
    lugar errado.

    Este teste força a diferença — `DATABASE_URL` vira o role CONTIDO,
    igual ao Staging — e verifica um efeito que só o Alembic produz e o
    `create_all()` nunca toca: a tabela `alembic_version`. Sem a correção,
    `command.upgrade` tenta criá-la pelo role sem `CREATE` e falha alto
    (`permission denied`), no banco vazio — nada aqui para o `create_all()`
    mascarar."""
    database, eng_app, eng_manut = _montar(monkeypatch, manutencao_e_dono=True)
    # A diferença que expõe o bug: `DATABASE_URL` (o que `env.py` usava antes
    # da correção) precisa ser DIFERENTE de `DATABASE_URL_MANUTENCAO` —
    # exatamente como no Staging (`cowdata_app` vs o role dono).
    monkeypatch.setattr(database, "DATABASE_URL", _url("app_teste_boot", _BANCO))
    try:
        database.create_db_and_tables()  # se levantar "permission denied", o bug voltou

        with eng_manut.connect() as conn:
            existe = conn.execute(sa.text(
                "SELECT to_regclass('public.alembic_version') IS NOT NULL"
            )).scalar()
        assert existe, "alembic_version tinha que ter sido criada pela conexão de dono"
    finally:
        eng_app.dispose()
        eng_manut.dispose()


def test_sem_a_conexao_de_dono_o_boot_e_recusado(monkeypatch, papeis):
    """O par do teste acima: prova que ele mede alguma coisa.

    Aqui as duas pontas são o role contido — que é exatamente o estado em que
    o Staging ficaria se `create_db_and_tables()` tivesse continuado na
    `engine` de sempre. O banco recusa, e a recusa é a API no chão.
    """
    database, eng_app, eng_manut = _montar(monkeypatch, manutencao_e_dono=False)
    try:
        with pytest.raises(sa.exc.ProgrammingError) as erro:
            database.create_db_and_tables()
        assert "permission denied" in str(erro.value).lower(), str(erro.value)[:300]
    finally:
        eng_app.dispose()
        eng_manut.dispose()
