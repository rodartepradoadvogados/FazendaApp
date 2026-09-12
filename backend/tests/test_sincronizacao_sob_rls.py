"""
Achado da auditoria do Painel CowData sob RLS (11/09/2026, ver
docs/security-audit/roteiro-seguranca.md): o mesmo sintoma do bug de
`session.commit()` ausente (PR #760, já corrigido) reaparece por uma causa
NOVA assim que RLS está ligado — POST /painel-cowdata/fazendas/{id}/
sincronizar copia dados de uma fazenda para outra na MESMA transação, e o
Painel CowData nunca tem uma fazenda selecionada no token (nenhuma das
duas fazendas bate com o contexto). Sob RLS, pela sessão comum da
requisição: a leitura da origem vem vazia, o DELETE do destino apaga 0
linhas — nada viola o `WITH CHECK` (não há linha pra inserir), então
`session.commit()` passa limpo e a rota devolve `"status": "ok"` com
`linhas_copiadas: 0` — sucesso falso, sem nenhum erro.

Corrigido trocando `Depends(get_session)` por
`Depends(get_session_manutencao)` na rota — mesmo padrão do fix de login,
mas cobrindo leitura E escrita (não só leitura).

Por que roda contra PostgreSQL de verdade: RLS não existe em SQLite. Pulado
sem `DATABASE_URL_POSTGRES_TESTE` — mesma convenção de test_login_sob_rls.py.
"""
from __future__ import annotations

import os
from datetime import date

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, criar_token, hash_senha
from fazenda.models import Animal, Fazenda, Parto, Usuario

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

pytestmark = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (RLS não existe em SQLite)",
)

_BANCO = "cowdata_teste_rls_sincronizacao"
_DONO = "cowdata_teste_sync_dono"
_APP = "cowdata_teste_sync_app"
_SENHA = "teste_rls_local"


def _url_para(banco: str, usuario: str | None = None) -> str:
    url = sa.engine.make_url(URL_ADMIN).set(database=banco)
    if usuario:
        url = url.set(username=usuario, password=_SENHA)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def banco_com_rls():
    """Mesmo desenho de test_login_sob_rls.py::banco_com_rls, com uma
    fazenda de origem (dado real) e uma fazenda de teste (destino,
    eh_teste=True) já cadastradas."""
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
        origem = Fazenda(nome="Jairo Nasser", ativa=True, eh_teste=False)
        destino = Fazenda(nome="Fazenda Teste", ativa=True, eh_teste=True)
        session.add_all([origem, destino])
        session.commit()
        session.refresh(origem)
        session.refresh(destino)
        origem_id, destino_id = origem.id, destino.id

        session.add(Animal(numero="1", fazenda_id=origem_id, sexo="F"))
        session.add(Parto(numero_matriz="1", fazenda_id=origem_id, data_parto=date(2026, 1, 1)))

        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        session.add(dono)
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
    yield engine_dono, engine_app, origem_id, destino_id

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
    """`get_session` devolve uma sessão contra `engine_app` (role restrito,
    equivalente ao `cowdata_app` de produção) com `session.info["fazenda_id"]
    = None` — exatamente o token do Painel CowData, que nunca tem "fid"."""
    engine_dono, engine_app, origem_id, destino_id = banco_com_rls
    monkeypatch.setattr(database, "engine_manutencao", engine_dono)

    def _get_session_override():
        with Session(engine_app) as session:
            session.info["fazenda_id"] = None
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, origem_id, destino_id
    main.app.dependency_overrides.clear()


def test_sincronizar_copia_dado_de_verdade_sob_rls(client):
    """A prova ponta a ponta: com a correção (rota usando
    get_session_manutencao), a sincronização precisa copiar as linhas de
    verdade, não devolver "status": "ok" com 0 linhas."""
    c, origem_id, destino_id = client
    token = criar_token("dono")
    r = c.post(
        f"/painel-cowdata/fazendas/{destino_id}/sincronizar",
        json={"origem_id": origem_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "ok"
    assert corpo["linhas_copiadas"] >= 2, (
        "sucesso falso — a rota respondeu 'ok' mas não copiou nada, reprodução do achado da auditoria de RLS"
    )
