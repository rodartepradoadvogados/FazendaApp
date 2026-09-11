"""
Incidente de 11/09/2026: ao ligar RLS em produção, o LOGIN parou de
funcionar — a tela de troca de fazenda mostrou "Fazenda Teste" e sumiu com a
fazenda real do dono (achado no teste de fumaça manual em produção,
reportado como "a fazenda real sumiu!"). Revertido na hora
(`docs/security-audit/roteiro-seguranca.md` tem o relato completo).

CAUSA RAIZ: `POST /auth/login` decide quais fazendas oferecer lendo
`UsuarioFazenda` ANTES de qualquer fazenda estar selecionada — não existe
"fid" no token de um login que ainda está acontecendo. Sob a política de
RLS (`fazenda_id = current_setting('app.fazenda_id', ...)`), essa consulta
nega TUDO em silêncio: sem contexto, nenhuma linha bate. O mesmo vale para
`POST /auth/selecionar-fazenda` (o contexto do token ainda não tem a
fazenda que a pessoa está tentando escolher) e para as checagens de
identidade da Equipe CowData (`eh_membro_equipe_cowdata`/
`eh_consultor_cowdata`, que leem a Pessoa do usuário numa fazenda quase
sempre DIFERENTE da hoje selecionada).

A correção (ver fazenda/auth.py e fazenda/api/routers/auth.py): estas
leituras passam a ir por `engine_manutencao` (role dono, sem RLS), não pela
`session` da requisição — mesmo raciocínio já usado para as rotinas de
fundo (roteiro-seguranca.md, seção 2): o filtro real de segurança é
`usuario_id`/`fazenda_id` explícito em Python, RLS nunca foi a defesa
verdadeira aqui, só um bloqueio cego de mais.

Por que roda contra PostgreSQL de verdade: RLS não existe em SQLite. Pulado
sem `DATABASE_URL_POSTGRES_TESTE` — mesma convenção de test_backup_sob_rls.py
e test_contexto_fazenda_sessao.py. O banco é criado e destruído pelo
próprio teste.
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

import fazenda.api.routers.auth as auth_router
import fazenda.api.routers.fazendas as fazendas_router
import fazenda.auth as auth_module
import fazenda.database as database
from fazenda.auth import hash_senha
from fazenda.models import Fazenda, Pessoa, Usuario, UsuarioFazenda

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

pytestmark = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (RLS não existe em SQLite)",
)

_BANCO = "cowdata_teste_rls_login"
_DONO = "cowdata_teste_login_dono"
_APP = "cowdata_teste_login_app"
_SENHA = "teste_rls_local"


def _url_para(banco: str, usuario: str | None = None) -> str:
    url = sa.engine.make_url(URL_ADMIN).set(database=banco)
    if usuario:
        url = url.set(username=usuario, password=_SENHA)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def banco_com_rls():
    """Mesmo desenho de test_backup_sob_rls.py::banco_com_rls — schema real,
    RLS ligado (sem FORCE) em toda tabela com `fazenda_id`, dois roles
    (dono/app). Aqui, além disso, semeia um Usuario com UM vínculo
    (UsuarioFazenda) — o suficiente para reproduzir o login quebrando, sem
    precisar de duas fazendas."""
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO}"))
        for role in (_DONO, _APP):
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {role}"))
            conn.execute(sa.text(f"CREATE ROLE {role} LOGIN NOSUPERUSER PASSWORD '{_SENHA}'"))
        conn.execute(sa.text(f"CREATE DATABASE {_BANCO} OWNER {_DONO}"))
    admin.dispose()

    engine_dono = sa.create_engine(_url_para(_BANCO, _DONO))
    SQLModel.metadata.create_all(engine_dono)

    with Session(engine_dono) as session:
        fazenda = Fazenda(nome="Fazenda Real do Cliente")
        session.add(fazenda)
        session.commit()
        session.refresh(fazenda)
        pessoa = Pessoa(nome="Jairo", tipo="Funcionário", fazenda_id=fazenda.id, ativo=True)
        session.add(pessoa)
        session.commit()
        session.refresh(pessoa)
        usuario = Usuario(
            username="jairo", nome="Jairo", senha_hash=hash_senha("123"), papel="admin",
            email="jairo@fazenda-real.com.br", pessoa_id=pessoa.id,
        )
        session.add(usuario)
        session.commit()
        session.refresh(usuario)
        session.add(UsuarioFazenda(usuario_id=usuario.id, fazenda_id=fazenda.id, contratante=True))
        session.commit()
        fazenda_id = fazenda.id
        usuario_id = usuario.id

    with engine_dono.begin() as conn:
        conn.execute(sa.text(f"GRANT USAGE ON SCHEMA public TO {_APP}"))
        conn.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_APP}"))
        conn.execute(sa.text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_APP}"))
        tabelas = [
            linha[0]
            for linha in conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'fazenda_id'"
                )
            )
        ]
        assert "usuario_fazenda" in tabelas, "o schema real precisa ter usuario_fazenda com fazenda_id"
        for tabela in tabelas:
            conn.execute(sa.text(f'ALTER TABLE "{tabela}" ENABLE ROW LEVEL SECURITY'))
            conn.execute(
                sa.text(
                    f'CREATE POLICY isolamento_fazenda ON "{tabela}" TO {_APP} '
                    "USING (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int) "
                    "WITH CHECK (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int)"
                )
            )

    engine_app = sa.create_engine(_url_para(_BANCO, _APP))
    yield engine_dono, engine_app, fazenda_id, usuario_id

    engine_app.dispose()
    engine_dono.dispose()
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        for role in (_APP, _DONO):
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {role}"))
    admin.dispose()


@pytest.fixture
def client(banco_com_rls, monkeypatch):
    """TestClient ponta a ponta: `get_session` devolve uma sessão contra
    `engine_app` (o role RESTRITO, equivalente ao `cowdata_app` de
    produção), com `session.info["fazenda_id"] = None` — exatamente o
    estado de um request de login, que nunca carrega "fid". O listener
    `_aplicar_contexto_de_fazenda` (database.py) aplica isso de verdade via
    `set_config`, então a política de RLS entra em ação igual a produção."""
    engine_dono, engine_app, fazenda_id, usuario_id = banco_com_rls

    # As funções corrigidas leem `engine_manutencao` do MÓDULO onde foram
    # importadas (fazenda.auth / api/routers/auth.py / api/routers/
    # fazendas.py) — sem isto, elas usariam a `engine_manutencao` de
    # verdade do processo (sem DATABASE_URL_MANUTENCAO no ambiente de
    # teste, cai na mesma `engine` de sempre, não no `engine_dono` deste
    # banco descartável), e o teste não provaria nada sobre o bug real.
    monkeypatch.setattr(auth_module, "engine_manutencao", engine_dono, raising=False)
    monkeypatch.setattr(auth_router, "engine_manutencao", engine_dono, raising=False)
    monkeypatch.setattr(fazendas_router, "engine_manutencao", engine_dono, raising=False)

    def _get_session_override():
        with Session(engine_app) as session:
            session.info["fazenda_id"] = None
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, fazenda_id, usuario_id
    main.app.dependency_overrides.clear()


def test_sem_a_correcao_a_consulta_pela_sessao_da_requisicao_nega_o_vinculo(banco_com_rls):
    """O ponto de partida, igual ao de test_backup_sob_rls.py: prova que a
    política nega em silêncio (zero linhas, não erro) quando a consulta usa
    a sessão da requisição (RLS-bound) sem contexto — é exatamente o que
    `_fazendas_vinculadas`/`_vinculo`/`minhas_fazendas` faziam antes da
    correção, e por que o login sumiu com a fazenda real em produção."""
    _, engine_app, fazenda_id, usuario_id = banco_com_rls
    with Session(engine_app) as session:
        session.info["fazenda_id"] = None
        from sqlmodel import select
        linhas = session.exec(
            select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario_id)
        ).all()
    assert linhas == [], "sem contexto, a política nega o vínculo em silêncio — a causa raiz do incidente"


def test_login_devolve_a_fazenda_real_do_usuario(client):
    """A prova ponta a ponta: com a correção (helpers lendo por
    `engine_manutencao`), POST /auth/login precisa devolver a fazenda de
    verdade do usuário — não uma lista vazia, mesmo sem "fid" nenhum no
    momento do login."""
    c, fazenda_id, _usuario_id = client
    r = c.post("/auth/login", json={"username": "jairo", "senha": "123"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    # 1 vínculo só e nenhuma opção CowData → auto-seleciona (mesma regra de
    # login(), "0 ou 1 fazenda → auto-seleciona"). O ponto crítico é que a
    # fazenda apareceu — sob o bug antigo, `fazendas` vinha vazia e
    # `fazenda_atual` não aparecia na resposta nenhuma.
    assert "fazenda_atual" in corpo, "a fazenda do usuário sumiu da resposta — reprodução do incidente"
    assert corpo["fazenda_atual"]["id"] == fazenda_id
    assert corpo["fazenda_atual"]["nome"] == "Fazenda Real do Cliente"


def test_contas_disponiveis_ve_a_fazenda_real_mesmo_com_token_de_outra_fazenda(client):
    """`GET /auth/contas-disponiveis` foi o endpoint que a tela "Trocar de
    conta" chamou em produção — com um token de sessão antigo (fid de uma
    OUTRA fazenda), a fazenda real do usuário sumiu da lista. Reproduz com
    um token que carrega um fid diferente do vínculo real."""
    c, fazenda_id, _usuario_id = client
    login = c.post("/auth/login", json={"username": "jairo", "senha": "123"})
    token = login.json()["token"]

    r = c.get("/auth/contas-disponiveis", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    ids = [o["id"] for o in r.json()["opcoes"]]
    assert fazenda_id in ids, "a fazenda real do usuário sumiu de 'Trocar de conta' — reprodução do incidente"
