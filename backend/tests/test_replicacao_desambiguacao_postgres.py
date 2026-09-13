"""
A sincronização da Fazenda Teste, ponta a ponta, contra um PostgreSQL de
verdade — o único lugar onde o defeito de 08/09/2026 aparece.

POR QUE NÃO EM SQLITE: lá uma coluna DATE aceita a string
`'2026-07-18::sandbox-diaria_dia-1'` sem reclamar (afinidade de tipo, não
tipagem). Os testes de replicação que já existem rodam em SQLite e ficaram
TODOS VERDES enquanto a sincronização respondia HTTP 500 em produção — foi
por isso que o defeito passou. Este arquivo fecha essa lacuna.

O CENÁRIO é o que o dono executou: fazenda do cliente com uma diária lançada,
copiada para a Fazenda Teste. Antes da correção, o Postgres respondia
`time zone "sandbox-diaria_dia-1" not recognized` e a cópia inteira abortava —
as 180 tabelas, não só a diária. Daí o sandbox aparecer vazio.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

import pytest
import sqlalchemy as sa
from sqlmodel import Session, SQLModel, create_engine, select

# Import no topo, e não dentro do teste: `SQLModel.metadata` só conhece as
# tabelas depois que os modelos são importados, e é a fixture — que roda antes
# do corpo do teste — quem chama `create_all`.
from fazenda.models import Fazenda
from fazenda.models.pessoal import Diaria, DiariaDia, Pessoa
from fazenda.rules.replicacao_fazenda import sincronizar_fazenda_teste_destrutivo

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

pytestmark = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (SQLite não tipa DATE)",
)

_BANCO = "cowdata_teste_replicacao"


@pytest.fixture
def engine():
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        conn.execute(sa.text(f"CREATE DATABASE {_BANCO}"))
    admin.dispose()

    # `render_as_string(hide_password=False)` e não `str()`: `str()` mascara a
    # senha como `***` e a conexão falha no CI (ver test_backup_sob_rls.py).
    eng = create_engine(
        sa.engine.make_url(URL_ADMIN).set(database=_BANCO).render_as_string(hide_password=False)
    )
    SQLModel.metadata.create_all(eng)
    yield eng

    eng.dispose()
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
    admin.dispose()


def test_sincronizar_com_diaria_lancada_nao_derruba_a_copia(engine):
    """O caso do dono, reproduzido: HTTP 500 e sandbox vazio.

    Revertendo a correção em `_colunas_para_desambiguar`, este teste fica
    VERMELHO com o mesmo erro de produção."""
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser", eh_teste=False))
        s.add(Fazenda(id=2, nome="Fazenda Teste", eh_teste=True))
        s.commit()

        pessoa = Pessoa(nome="Diarista", tipo="funcionario", fazenda_id=1)
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)

        diaria = Diaria(
            pessoa_id=pessoa.id, valor_diaria=120.0,
            data_inicio=date(2026, 7, 1), fazenda_id=1,
        )
        s.add(diaria)
        s.commit()
        s.refresh(diaria)

        # A linha que quebrava: `UniqueConstraint(diaria_id, data)`, com `data`
        # DATE — a coluna em que o sufixo de texto era grudado.
        s.add(DiariaDia(diaria_id=diaria.id, data=date(2026, 7, 18), trabalhado=False, fazenda_id=1))
        s.commit()

    with Session(engine) as s:
        resultado = sincronizar_fazenda_teste_destrutivo(s, origem_id=1, destino_id=2)
        s.commit()

    assert resultado is not None

    with Session(engine) as s:
        copiadas = s.exec(select(DiariaDia).where(DiariaDia.fazenda_id == 2)).all()
        assert len(copiadas) == 1, "a diária da origem tinha que aparecer na Fazenda Teste"
        assert copiadas[0].data == date(2026, 7, 18), (
            "a data foi copiada fiel — sem o sufixo `::sandbox-...` que o Postgres recusa"
        )
