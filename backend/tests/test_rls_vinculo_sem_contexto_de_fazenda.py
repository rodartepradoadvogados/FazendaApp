"""
Bug relatado pelo usuário em 12/09/2026 (funcionário travado logo após o
login, "Não foi possível carregar" em toda tela): sob RLS de verdade, duas
funções de `fazenda/auth.py` — `resolver_fazenda_id_escrita` e a checagem de
vínculo dentro de `exigir_fazenda_selecionada` — liam `UsuarioFazenda` pela
sessão comum, ANTES de qualquer fazenda ter sido selecionada (é exatamente
o que elas estão tentando descobrir). Nesse momento `app.fazenda_id` está
vazio, e a política `isolamento_fazenda` nega qualquer linha — mesmo o
vínculo único e real do usuário. As duas passaram a usar
`sessao_sem_recorte_de_fazenda` (mesmo padrão já usado por
`eh_membro_equipe_cowdata` desde o incidente de 11/09/2026, documentado em
`database.py`).

Reproduzido aqui contra um PostgreSQL de verdade, com RLS de verdade
(policy idêntica à de produção, ver docs/security-audit/rls-migracao-
proposta.sql) — SQLite (o resto da suíte) não tem `set_config`/RLS, então
nunca teria pego este bug.
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlmodel import Session, SQLModel

import fazenda.auth as auth
import fazenda.database as database
from fazenda.models import Fazenda, Usuario, UsuarioFazenda

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

_precisa_postgres = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (SQLite não tem RLS)",
)

_BANCO = "cowdata_teste_rls_vinculo"
_ROLE_APP = "cowdata_app_teste_vinculo"


def _url(banco: str, role: str | None = None, senha: str | None = None) -> str:
    u = sa.engine.make_url(URL_ADMIN).set(database=banco)
    if role:
        u = u.set(username=role, password=senha)
    return u.render_as_string(hide_password=False)


@pytest.fixture
def cenario_rls():
    """Banco descartável com `usuario`/`fazenda`/`usuario_fazenda` reais,
    RLS ligado em `usuario_fazenda` com a mesma política de produção, um
    vínculo real de 1 usuário -> 1 fazenda, e um role restrito (sem
    BYPASSRLS) para simular a conexão da aplicação."""
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        conn.execute(sa.text(f"CREATE DATABASE {_BANCO}"))
        conn.execute(sa.text(f"DROP ROLE IF EXISTS {_ROLE_APP}"))
        conn.execute(sa.text(f"CREATE ROLE {_ROLE_APP} LOGIN PASSWORD 'teste123' NOSUPERUSER"))
    admin.dispose()

    engine_dono = sa.create_engine(_url(_BANCO))
    SQLModel.metadata.create_all(engine_dono)
    with engine_dono.connect() as conn:
        conn.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON usuario, fazenda, usuario_fazenda TO {_ROLE_APP}"))
        for seq in ("usuario_id_seq", "fazenda_id_seq", "usuario_fazenda_id_seq"):
            conn.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO {_ROLE_APP}"))
        conn.execute(sa.text("ALTER TABLE usuario_fazenda ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY isolamento_fazenda ON usuario_fazenda TO {_ROLE_APP} "
            "USING (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int) "
            "WITH CHECK (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int)"
        ))
        conn.commit()

    with Session(engine_dono) as s:
        usuario = Usuario(username="funcionario_teste", senha_hash="x", papel="funcionario", ativo=True, permissoes="agenda")
        fazenda = Fazenda(nome="Fazenda RLS Teste")
        s.add(usuario); s.add(fazenda); s.commit(); s.refresh(usuario); s.refresh(fazenda)
        s.add(UsuarioFazenda(usuario_id=usuario.id, fazenda_id=fazenda.id))
        s.commit()
        usuario_id, fazenda_id = usuario.id, fazenda.id
    engine_dono.dispose()

    engine_app = sa.create_engine(_url(_BANCO, _ROLE_APP, "teste123"))
    yield engine_dono, engine_app, usuario_id, fazenda_id
    engine_app.dispose()

    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        conn.execute(sa.text(f"DROP ROLE IF EXISTS {_ROLE_APP}"))
    admin.dispose()


@_precisa_postgres
def test_sessao_comum_fica_cega_para_o_vinculo_sem_contexto(cenario_rls):
    """Prova que o cenário reproduz o bug de verdade: sob a role restrita
    (RLS de verdade, sem BYPASSRLS), sem `app.fazenda_id` ainda definido, a
    linha do `UsuarioFazenda` — que EXISTE — não aparece pela sessão comum.
    Se este teste falhar, os outros dois abaixo não estão testando nada."""
    from sqlmodel import select
    _, engine_app, usuario_id, _fazenda_id = cenario_rls
    with Session(engine_app) as session:
        session.info["fazenda_id"] = None
        linhas = session.exec(
            select(UsuarioFazenda.fazenda_id).where(UsuarioFazenda.usuario_id == usuario_id)
        ).all()
        assert linhas == []


@_precisa_postgres
def test_resolver_fazenda_id_escrita_acha_o_vinculo_mesmo_sem_contexto(cenario_rls, monkeypatch):
    """O fix: `resolver_fazenda_id_escrita` usa `sessao_sem_recorte_de_fazenda`
    — precisa continuar resolvendo a fazenda certa de um usuário com
    exatamente 1 vínculo, mesmo chamada ANTES de qualquer fazenda
    selecionada (é o cenário de todo login novo)."""
    _, engine_app, usuario_id, fazenda_id = cenario_rls
    # `sessao_sem_recorte_de_fazenda` usa `engine_manutencao`, montada uma vez
    # na importação do módulo a partir de DATABASE_URL_MANUTENCAO — aqui
    # trocamos o engine já montado para apontar para o MESMO banco deste
    # teste, pela conexão sem RLS (dono/superuser).
    # usa `engine_manutencao`, montada uma vez na importação do módulo a
    # partir da env var; aqui trocamos o engine já montado para apontar
    # para o MESMO banco deste teste, pela conexão sem RLS (admin).
    monkeypatch.setattr(database, "engine_manutencao", sa.create_engine(URL_ADMIN.rsplit("/", 1)[0] + "/" + _BANCO))

    with Session(engine_app) as session:
        session.info["fazenda_id"] = None
        usuario = session.get(Usuario, usuario_id)
        resultado = auth.resolver_fazenda_id_escrita(session, usuario, None)
    assert resultado == fazenda_id
