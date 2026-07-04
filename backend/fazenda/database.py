"""
Conexão com o banco de dados e criação das tabelas.
Usa SQLite em desenvolvimento, PostgreSQL em produção (via DATABASE_URL).
"""
from sqlmodel import Session, SQLModel, create_engine

from fazenda.config import settings

is_sqlite = "sqlite" in settings.database_url

engine_kwargs: dict = {
    "echo": settings.environment == "development",
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL: pool pre-ping para reconectar automaticamente
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10

engine = create_engine(settings.database_url, **engine_kwargs)


def create_db_and_tables() -> None:
    """Cria todas as tabelas (idempotente — usa CREATE TABLE IF NOT EXISTS)."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency injection do FastAPI para obter uma sessão de banco."""
    with Session(engine) as session:
        yield session
