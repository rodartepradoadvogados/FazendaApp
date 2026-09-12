"""
Achado da auditoria do Painel CowData sob RLS (11/09/2026, ver
docs/security-audit/roteiro-seguranca.md): os botões "aplicar em todas as
fazendas de uma vez" (Parâmetros, Cadastros globais, Farmácia) fazem um
laço sobre as fazendas-cliente, lendo e ESCREVENDO `fazenda_id` explícito
— sem nenhuma fazenda selecionada no token do Painel CowData. Sob RLS, pela
sessão comum, a escrita da primeira fazenda do laço já viola o
`WITH CHECK` da política → erro 500 duro, transação inteira aborta.

Este arquivo testa o representante mais simples do padrão —
PUT /painel-cowdata/parametros/{chave} — corrigido com
`Depends(get_session_manutencao)`. O mecanismo é idêntico nos três
botões (mesma correção já aplicada em painel_cowdata_cadastros.py e
painel_cowdata_farmacia.py); não repetido teste por teste aqui.

Por que roda contra PostgreSQL de verdade: RLS não existe em SQLite. Pulado
sem `DATABASE_URL_POSTGRES_TESTE` — mesma convenção dos demais
test_*_sob_rls.py.
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, criar_token, hash_senha
from fazenda.models import Fazenda, ParametroFazenda, Usuario

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

pytestmark = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (RLS não existe em SQLite)",
)

_BANCO = "cowdata_teste_rls_massa"
_DONO = "cowdata_teste_massa_dono"
_APP = "cowdata_teste_massa_app"
_SENHA = "teste_rls_local"


def _url_para(banco: str, usuario: str | None = None) -> str:
    url = sa.engine.make_url(URL_ADMIN).set(database=banco)
    if usuario:
        url = url.set(username=usuario, password=_SENHA)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def banco_com_rls():
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
        fazenda = Fazenda(nome="Fazenda Cliente", ativa=True, eh_teste=False)
        session.add(fazenda)
        session.commit()
        session.refresh(fazenda)
        fazenda_id = fazenda.id

        session.add(ParametroFazenda(
            chave="pev_dias", fazenda_id=None, grupo="reproducao", label="PEV (dias)",
            valor="60", tipo="int", unidade="dias",
        ))
        session.add(Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        session.commit()

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
        catalogo_global = {"parametro_fazenda"}  # só a que este teste usa, mas a mesma lógica vale pra todas as 18
        for tabela in tabelas:
            conn.execute(sa.text(f'ALTER TABLE "{tabela}" ENABLE ROW LEVEL SECURITY'))
            leitura = (
                "fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int OR fazenda_id IS NULL"
                if tabela in catalogo_global
                else "fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int"
            )
            conn.execute(
                sa.text(
                    f'CREATE POLICY isolamento_fazenda ON "{tabela}" TO {_APP} '
                    f"USING ({leitura}) "
                    "WITH CHECK (fazenda_id = NULLIF(current_setting('app.fazenda_id', true), '')::int)"
                )
            )

    engine_app = sa.create_engine(_url_para(_BANCO, _APP))
    yield engine_dono, engine_app, fazenda_id

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
    engine_dono, engine_app, fazenda_id = banco_com_rls
    monkeypatch.setattr(database, "engine_manutencao", engine_dono)

    def _get_session_override():
        with Session(engine_app) as session:
            session.info["fazenda_id"] = None
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine_dono, fazenda_id
    main.app.dependency_overrides.clear()


def test_aplicar_em_todas_as_fazendas_nao_quebra_sob_rls(client):
    """Sem a correção, este PUT falharia com 500 (WITH CHECK) na primeira
    fazenda do laço — e mesmo a atualização da linha global (fazenda_id
    None) falharia, porque o WITH CHECK do RLS não tem exceção para NULL."""
    c, engine_dono, fazenda_id = client
    token = criar_token("dono")
    r = c.put(
        "/painel-cowdata/parametros/pev_dias",
        json={"valor": 45},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["global_atualizado"] is True
    assert corpo["atualizados"] == 1

    with Session(engine_dono) as verificacao:
        linhas = verificacao.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "pev_dias")).all()
    por_fazenda = {l.fazenda_id: l.valor for l in linhas}
    assert por_fazenda[None] == "45", "linha global (fazenda_id=None) não foi atualizada — reprodução do 500 de WITH CHECK"
    assert por_fazenda[fazenda_id] == "45", "linha da fazenda-cliente não foi criada/atualizada — reprodução do bug"
