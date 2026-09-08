"""
O backup sob RLS, em PostgreSQL de verdade.

Este é o teste que a conclusão da seção 8 de `docs/security-audit/rls-proposta.md`
exigia virar código antes de qualquer política entrar em produção. Ele prova as
duas metades da mesma frase:

1. **Sob RLS, a conexão da aplicação não serve para backup.** A política nega
   por falta de contexto de fazenda, e o `SELECT` não levanta exceção nenhuma —
   devolve vazio. Sem a guarda de `rules/backup.py`, o caminho feliz rodaria
   inteiro: ZIP de cabeçalhos, e-mail enviado, `sucesso=True` gravado, e a
   próxima tentativa só daí a `INTERVALO_DIAS`.
2. **A conexão de manutenção (role dono, políticas sem `FORCE`) traz linha de
   verdade.** É o desenho aprovado, e o que `database.py::engine_manutencao`
   implementa — sem criar nenhum role `BYPASSRLS` que qualquer código da API
   pudesse assumir.

Por que não roda em SQLite: RLS não existe lá. Este arquivo só roda com um
PostgreSQL de verdade, apontado por `DATABASE_URL_POSTGRES_TESTE`
(ex.: `postgresql://postgres@localhost:5432/postgres`), e é pulado sem ela. O
CI o executa no job `backend-tests-postgres`, que sobe o serviço.

O banco é criado e destruído pelo próprio teste — nunca reaproveite aqui a URL
de um banco com dado que importe.
"""
from __future__ import annotations

import os
import zipfile
from io import BytesIO

import pytest
import sqlalchemy as sa
from sqlmodel import Session, SQLModel, select

import fazenda.rules.backup as backup_module
from fazenda.models import Animal, BackupAutomatico, Fazenda

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

pytestmark = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (RLS não existe em SQLite)",
)

_BANCO = "cowdata_teste_rls_backup"
_DONO = "cowdata_teste_dono"
_APP = "cowdata_teste_app"


def _url_para(banco: str, usuario: str | None = None) -> str:
    url = sa.engine.make_url(URL_ADMIN).set(database=banco)
    return str(url.set(username=usuario) if usuario else url)


@pytest.fixture(scope="module")
def banco_com_rls():
    """Banco descartável com o schema real, uma linha de dado e RLS ligado.

    RLS ENABLE **sem FORCE**, de propósito: é o desenho da seção 8. O `FORCE` só
    alcançaria o dono das tabelas — que é justamente quem precisa enxergar tudo
    para o backup — e, medido, o dono pode removê-lo sozinho com um comando, o
    que faz dele teatro e não proteção.
    """
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO}"))
        for role in (_DONO, _APP):
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {role}"))
            conn.execute(sa.text(f"CREATE ROLE {role} LOGIN NOSUPERUSER"))
        conn.execute(sa.text(f"CREATE DATABASE {_BANCO} OWNER {_DONO}"))
    admin.dispose()

    engine_dono = sa.create_engine(_url_para(_BANCO, _DONO))
    SQLModel.metadata.create_all(engine_dono)

    with Session(engine_dono) as session:
        fazenda = Fazenda(nome="Fazenda do teste de RLS")
        session.add(fazenda)
        session.commit()
        session.refresh(fazenda)
        session.add(
            Animal(numero="42", categoria_abrev="Vaca", sexo="F", ativo=True, fazenda_id=fazenda.id)
        )
        session.commit()
        fazenda_id = fazenda.id

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
        assert tabelas, "o schema real precisa ter tabelas com fazenda_id"
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
    yield engine_dono, engine_app, fazenda_id

    engine_app.dispose()
    engine_dono.dispose()
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        for role in (_APP, _DONO):
            conn.execute(sa.text(f"DROP ROLE IF EXISTS {role}"))
    admin.dispose()


def test_a_politica_esconde_o_dado_da_conexao_da_aplicacao_sem_erro(banco_com_rls):
    """O ponto de partida, e o que torna o resto necessário: RLS não falha
    ruidosamente, ele devolve vazio. Se este teste um dia passar a ver erro em
    vez de zero linha, a guarda do backup deixou de ser necessária — mas até
    lá, ela é a única coisa entre o RLS e um backup oco carimbado de sucesso."""
    _, engine_app, _ = banco_com_rls
    with Session(engine_app) as session:
        total = session.execute(sa.text("SELECT count(*) FROM animal")).scalar()
    assert total == 0, "sem contexto de fazenda a política nega — e nega calada"


def test_backup_pela_conexao_da_aplicacao_sai_vazio_e_e_recusado(banco_com_rls, monkeypatch):
    """O cenário que o RLS criaria, ponta a ponta, com o backup real."""
    _, engine_app, _ = banco_com_rls
    enviados = []
    monkeypatch.setattr(
        backup_module, "enviar_email",
        lambda destinatario, assunto, corpo, anexo_nome=None, anexo_bytes=None: enviados.append(
            (assunto, anexo_nome)
        ),
    )

    with Session(engine_app) as session:
        zip_bytes, linhas = backup_module.gerar_backup_zip(session)

    assert linhas == 0
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert zf.read("animal.csv").decode("utf-8-sig") == "", (
            "sob RLS o CSV sai sem NADA — nem cabeçalho, porque não há linha para tirar as colunas"
        )

    with Session(engine_app) as session:
        rodou = backup_module.executar_backup_se_necessario(session)

    assert rodou is True
    with Session(engine_app) as session:
        registros = session.exec(select(BackupAutomatico)).all()
        assert [r.sucesso for r in registros] == [False]
        assert "vazio" in registros[0].erro.lower()

    assert len(enviados) == 1
    assunto, anexo_nome = enviados[0]
    assert "FALHOU" in assunto
    assert anexo_nome is None


def test_backup_pela_conexao_de_manutencao_traz_linha_de_verdade(banco_com_rls, monkeypatch):
    """A outra metade: é isto que faz o desenho funcionar em vez de só evitar o
    dano. Com as políticas sem `FORCE`, o dono das tabelas enxerga o banco
    inteiro — e é essa a conexão que `engine_manutencao` entrega ao backup."""
    engine_dono, _, _ = banco_com_rls
    anexos = []
    monkeypatch.setattr(
        backup_module, "enviar_email",
        lambda destinatario, assunto, corpo, anexo_nome=None, anexo_bytes=None: anexos.append(
            (assunto, anexo_nome, anexo_bytes)
        ),
    )

    with Session(engine_dono) as session:
        zip_bytes, linhas = backup_module.gerar_backup_zip(session)

    assert linhas >= 1, "pela conexão de manutenção o backup TEM que ver o dado"
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        conteudo = zf.read("animal.csv").decode("utf-8-sig")
    assert "42" in conteudo, "o número do animal precisa estar dentro do CSV"

    with Session(engine_dono) as session:
        rodou = backup_module.executar_backup_se_necessario(session)

    assert rodou is True
    assert len(anexos) == 1
    assunto, anexo_nome, anexo_bytes = anexos[0]
    assert "FALHOU" not in assunto
    assert anexo_nome.endswith(".zip")
    assert anexo_bytes


def test_a_aplicacao_com_contexto_continua_enxergando_a_propria_fazenda(banco_com_rls):
    """Guarda contra o conserto errado: fazer o backup funcionar afrouxando a
    política. Com o contexto setado, a aplicação vê o dado da sua fazenda — se
    este teste passar a ver dado sem `SET LOCAL`, alguém desligou o isolamento
    em vez de resolver o backup."""
    _, engine_app, fazenda_id = banco_com_rls
    with engine_app.begin() as conn:
        conn.execute(sa.text(f"SET LOCAL app.fazenda_id = '{fazenda_id}'"))
        com_contexto = conn.execute(sa.text("SELECT count(*) FROM animal")).scalar()
    with engine_app.begin() as conn:
        conn.execute(sa.text(f"SET LOCAL app.fazenda_id = '{fazenda_id + 1}'"))
        outra_fazenda = conn.execute(sa.text("SELECT count(*) FROM animal")).scalar()

    assert com_contexto == 1
    assert outra_fazenda == 0
