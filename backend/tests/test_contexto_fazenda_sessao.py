"""
O mecanismo de contexto de fazenda por requisição: `database.get_session()`
marca `session.info["fazenda_id"]` a partir do token, e o listener
`_aplicar_contexto_de_fazenda` (SQLAlchemy `after_begin`) aplica
`set_config('app.fazenda_id', ...)` a cada transação nova da sessão — é o
que a política de RLS (quando entrar) vai ler.

O QUE ESTÁ SENDO PROTEGIDO, em ordem:

1. **O contexto é aplicado na abertura da sessão.** A base de tudo — sem
   isto, a política não teria o que ler.
2. **O contexto é REAPLICADO depois de um `commit()` no meio da sessão** —
   o risco central que motivou este desenho em vez de um `SET LOCAL`
   disparado uma única vez dentro de `get_session()`: o padrão do projeto é
   `session.add(...); session.commit()` várias vezes dentro da mesma rota
   (462 `session.commit()` só nos routers). Cada `commit()` fecha a
   transação e abre outra por trás (autobegin do SQLAlchemy) — um
   `SET LOCAL` de disparo único valeria só para a primeira leva de queries.
3. **Token sem fazenda ("fid" ausente) marca `None`, e vira `set_config`
   com NULL** — é o "sem contexto nega tudo" da política.
4. **SQLite (a suíte inteira) permanece inerte**, e **sessão sem a chave
   `"fazenda_id"` em `session.info` não aciona `set_config` nenhum** — os
   dois testes que não mudam o comportamento de nenhum teste já existente.

Os dois primeiros rodam contra PostgreSQL de verdade (SQLite não tem
`set_config`, e é justamente esse o comportamento medido). Os dois últimos
testam o listener isolado, sem precisar de banco nenhum de verdade.
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

import fazenda.database as database
from fazenda.auth import criar_token
from fazenda.database import _aplicar_contexto_de_fazenda

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

_precisa_postgres = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (SQLite não tem set_config)",
)

_BANCO = "cowdata_teste_contexto_fazenda"


def _url(banco: str) -> str:
    # `render_as_string(hide_password=False)` e não `str()`: `str()` mascara a
    # senha como `***` (ver test_backup_sob_rls.py).
    return sa.engine.make_url(URL_ADMIN).set(database=banco).render_as_string(hide_password=False)


@pytest.fixture
def engine_postgres():
    """Banco descartável, vazio — este mecanismo não depende de schema
    nenhum, só do listener e da sessão."""
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        conn.execute(sa.text(f"CREATE DATABASE {_BANCO}"))
    admin.dispose()

    engine = sa.create_engine(_url(_BANCO))
    yield engine

    engine.dispose()
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
    admin.dispose()


def _contexto_atual(session) -> str | None:
    return session.execute(sa.text("SELECT current_setting('app.fazenda_id', true)")).scalar()


@_precisa_postgres
def test_contexto_aplicado_na_abertura_da_sessao(engine_postgres, monkeypatch):
    monkeypatch.setattr(database, "engine", engine_postgres)
    token = criar_token("dono", fazenda_id=7)

    gen = database.get_session(authorization=f"Bearer {token}")
    session = next(gen)
    try:
        assert _contexto_atual(session) == "7"
    finally:
        gen.close()


@_precisa_postgres
def test_contexto_reaplicado_apos_commit_no_meio_da_sessao(engine_postgres, monkeypatch):
    """O teste que mais importa deste arquivo: prova o motivo de existir o
    listener `after_begin` em vez de um `SET LOCAL` só na abertura. Se este
    teste falhar, um `commit()` no meio de uma rota qualquer apagaria o
    contexto de fazenda pro resto da requisição — em silêncio, sob RLS."""
    monkeypatch.setattr(database, "engine", engine_postgres)
    token = criar_token("dono", fazenda_id=9)

    gen = database.get_session(authorization=f"Bearer {token}")
    session = next(gen)
    try:
        assert _contexto_atual(session) == "9"
        session.commit()  # fecha a transação; a próxima instrução abre outra (autobegin)
        assert _contexto_atual(session) == "9", (
            "o contexto tinha que ter sido reaplicado na transação nova"
        )
    finally:
        gen.close()


@_precisa_postgres
def test_token_sem_fazenda_grava_null(engine_postgres, monkeypatch):
    """Token sem "fid" (usuário sem fazenda vinculada, ou as rotas do Painel
    CowData/auth/fazendas, que operam sem fazenda selecionada por
    definição) marca `session.info["fazenda_id"] = None` — o listener chama
    `set_config('app.fazenda_id', NULL, true)`, e o Postgres devolve
    string vazia para `current_setting`, não NULL de verdade (por isso a
    política usa `NULLIF(current_setting(...), '')`, ver rls-proposta.md,
    seção 4) — é o "sem contexto nega tudo"."""
    monkeypatch.setattr(database, "engine", engine_postgres)
    token = criar_token("dono")  # sem fazenda_id

    gen = database.get_session(authorization=f"Bearer {token}")
    session = next(gen)
    try:
        assert _contexto_atual(session) == ""
    finally:
        gen.close()


class _ConexaoFalsa:
    """Uma conexão de mentira: só para testar o listener isolado, sem
    precisar de banco nenhum de verdade."""

    def __init__(self, dialeto: str):
        self.dialect = type("DialetoFalso", (), {"name": dialeto})()
        self.chamadas: list = []

    def execute(self, *args, **kwargs):
        self.chamadas.append((args, kwargs))


class _SessaoFalsa:
    def __init__(self, info: dict):
        self.info = info


def test_sqlite_permanece_inerte():
    """A suíte inteira (milhares de testes) roda em SQLite — o listener
    dispara para toda `Session` do projeto, mas sob SQLite tem que sair sem
    tocar a conexão: `set_config` nem existe lá, e RLS também não."""
    conexao = _ConexaoFalsa("sqlite")
    sessao = _SessaoFalsa(info={"fazenda_id": 3})
    _aplicar_contexto_de_fazenda(sessao, transaction=None, connection=conexao)
    assert conexao.chamadas == []


def test_sessao_sem_marca_nao_aciona_set_config():
    """Sessão comum, sem `get_session()` por trás — a imensa maioria dos
    testes já existentes, e todo código que abre `Session(engine)` direto
    sem marcar nada — não pode acionar `set_config` nenhum."""
    conexao = _ConexaoFalsa("postgresql")
    sessao = _SessaoFalsa(info={})  # nunca marcada
    _aplicar_contexto_de_fazenda(sessao, transaction=None, connection=conexao)
    assert conexao.chamadas == []
