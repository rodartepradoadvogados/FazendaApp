from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Reaproveita a mesma normalização de URL e o metadata de modelos do app —
# import local (não no topo do módulo) para o `alembic` CLI não exigir que o
# resto do pacote `fazenda` já esteja configurado antes disso.
#
# BUG CORRIGIDO EM 10/09/2026: esta linha importava e usava `DATABASE_URL` (o
# role de aplicação, contido pela política de RLS) em vez de
# `DATABASE_URL_MANUTENCAO` (o role dono das tabelas) — e como
# `config` aqui é o MESMO objeto `cfg` que `database.py::_aplicar_alembic()`
# monta com a URL de dono antes de chamar `command.upgrade(cfg, "head")`,
# esta linha SOBRESCREVIA silenciosamente essa URL assim que `env.py` era
# carregado (`command.upgrade` → `script.run_env()` → este arquivo). Toda
# migração de verdade — a que só roda no ambiente com `cowdata_app` restrito,
# como o Staging — passava a tentar `ALTER TABLE` pela conexão ERRADA, e
# falhava com "must be owner of table X" (achado ao aplicar o DDL de RLS no
# Staging, ver docs/security-audit/roteiro-seguranca.md, item 3.1). Passou
# despercebido porque `create_db_and_tables()` roda `SQLModel.metadata.
# create_all(engine_manutencao)` logo em seguida como rede de segurança —
# isso cobre CRIAR tabela nova (o teste `test_boot_conexao_dono.py` só mede
# isso), mas nunca alterar uma tabela que já existe, que é o caso real.
#
# `DATABASE_URL_MANUTENCAO` já cai em `DATABASE_URL` quando a variável de
# ambiente não está definida (ver database.py) — então usar direto aqui é
# estritamente mais correto e não muda nada em ambiente sem o role separado
# (a suíte inteira, e a produção de hoje).
from fazenda.database import DATABASE_URL_MANUTENCAO  # noqa: E402
from fazenda.models import SQLModel  # noqa: E402

# `%` dobrado pelo mesmo motivo de `_aplicar_alembic()`: `set_main_option`
# grava num ConfigParser, que interpreta `%` como interpolação.
config.set_main_option("sqlalchemy.url", DATABASE_URL_MANUTENCAO.replace("%", "%%"))
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
