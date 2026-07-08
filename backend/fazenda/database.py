"""
Conexão com o banco de dados e criação das tabelas.
Usa SQLite em desenvolvimento, PostgreSQL em produção (via DATABASE_URL).
"""
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from fazenda.config import settings

# Railway/Heroku entregam DATABASE_URL como 'postgres://', que o SQLAlchemy 2.0
# não reconhece (Can't load plugin: sqlalchemy.dialects:postgres). Normaliza.
DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_sqlite = "sqlite" in DATABASE_URL

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

engine = create_engine(DATABASE_URL, **engine_kwargs)


# Migração leve: colunas adicionadas a tabelas que já podem existir em produção.
# O create_all não altera tabelas existentes, então adicionamos manualmente.
_COLUNAS_NOVAS: dict[str, list[tuple[str, str]]] = {
    "controle_leiteiro": [("raca", "VARCHAR")],
    "animal": [("sexo", "VARCHAR"), ("eh_semen", "BOOLEAN"), ("grupo_manual", "BOOLEAN")],
    "usuario": [("permissoes", "VARCHAR")],
    "conta_gerencial": [
        ("numero_lancamento", "VARCHAR"),
        ("data_prevista_entrada", "DATE"),
        ("data_pedido", "DATE"),
        ("entregue", "BOOLEAN"),
        ("tipo_documento", "VARCHAR"),
        ("numero_documento_pagamento", "VARCHAR"),
        ("conta_bancaria", "VARCHAR"),
        ("quantidade", "FLOAT"),
        ("valor_unitario", "FLOAT"),
        ("desconto_acrescimo", "FLOAT"),
        ("parcela_num", "INTEGER"),
        ("parcela_total", "INTEGER"),
        ("responsavel", "VARCHAR"),
        ("origem", "VARCHAR"),
        ("desconto_nota", "FLOAT"),
        ("acrescimo_nota", "FLOAT"),
    ],
}


def _migrar_colunas() -> None:
    insp = inspect(engine)
    tabelas = set(insp.get_table_names())
    with engine.begin() as conn:
        for tabela, colunas in _COLUNAS_NOVAS.items():
            if tabela not in tabelas:
                continue  # create_all já criou com o schema completo
            existentes = {c["name"] for c in insp.get_columns(tabela)}
            for nome, tipo in colunas:
                if nome not in existentes:
                    conn.execute(text(f'ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}'))


def create_db_and_tables() -> None:
    """Cria as tabelas (idempotente) e aplica migrações leves de colunas."""
    SQLModel.metadata.create_all(engine)
    _migrar_colunas()


def get_session():
    """Dependency injection do FastAPI para obter uma sessão de banco."""
    with Session(engine) as session:
        yield session
