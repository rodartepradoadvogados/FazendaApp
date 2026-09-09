"""
A migração que compõe as FKs entre tabelas de fazenda — `(col, fazenda_id)
REFERENCES pai(id, fazenda_id)` —, num PostgreSQL de verdade.

Por que não em SQLite: lá não existe a validação de dado que uma
`ADD CONSTRAINT` faz sobre linha já existente, que é o comportamento medido
aqui. Roda no CI, no job `backend-tests-postgres`.

O QUE ESTÁ SENDO PROTEGIDO, em ordem:

1. **A API não pode deixar de subir.** Mesma razão de
   `test_migracao_fazenda_id_not_null.py`: esta migração roda dentro de
   `_aplicar_alembic()`, chamada no boot. Uma FK que falhar ao compor — porque
   alguma linha em produção tem `fazenda_id` diferente do pai que referencia,
   ou seja, uma referência cruzada entre fazendas ATIVA — é PULADA, com a
   tabela voltando para a FK simples de antes. Nunca sem NENHUMA FK, e nunca
   derrubando as outras 119.
2. **A FK composta fecha o furo de verdade.** Depois de composta, gravar uma
   linha cujo pai é de OUTRA fazenda tem que ser recusado pelo banco — hoje a
   FK simples deixa passar.
3. **O catálogo global continua simples.** Compor contra um pai cujo
   `fazenda_id` é legitimamente NULL (`(id, NULL)`) quebraria o
   compartilhamento — achado 1 de `fks-compostas.md`.
4. **Uma violação real é PULADA e relatada, não escondida** — é o
   comportamento mais importante deste arquivo, porque uma falha aqui é
   provavelmente um vazamento entre fazendas descoberto no processo.
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")

pytestmark = pytest.mark.skipif(
    not URL_ADMIN,
    reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE (SQLite não valida FK sobre dado existente)",
)

_BANCO = "cowdata_teste_fks_compostas"


def _modulo():
    import importlib.util
    from pathlib import Path

    arquivo = (
        Path(__file__).resolve().parent.parent
        / "alembic" / "versions" / "472f92e0860b_fks_compostas_tenant.py"
    )
    spec = importlib.util.spec_from_file_location("mig_fks_compostas", arquivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Op:
    """`op.get_bind()` fora do Alembic: devolve a conexão do teste."""

    def __init__(self, conn):
        self._conn = conn

    def get_bind(self):
        return self._conn


@pytest.fixture
def banco():
    """Banco descartável com quatro cenários pequenos — não o esquema real
    (que muda toda semana): o que se mede aqui é o COMPORTAMENTO da migração
    diante de cada situação.

    (1) `lote`/`animal`: par saudável, FK simples hoje, filha aponta pro pai
        da MESMA fazenda — tem que compor.
    (2) `servico`: aponta pro MESMO `lote`, mas de OUTRA fazenda — a FK
        simples de hoje deixa passar (só olha `lote.id`); é a referência
        cruzada que a composição existe para fechar, e que faz a composição
        FALHAR — tem que ser pulada, não abortar a migração.
    (3) `principio_ativo`/`receita`: pai de catálogo global (`fazenda_id`
        NULL de propósito) — não pode ser composto.
    (4) `categoria`: auto-referência (`categoria_pai_id -> categoria.id`) —
        a UNIQUE tem que existir antes da própria FK poder usá-la.
    """
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
        conn.execute(sa.text(f"CREATE DATABASE {_BANCO}"))
    admin.dispose()

    engine = sa.create_engine(
        sa.engine.make_url(URL_ADMIN).set(database=_BANCO).render_as_string(hide_password=False)
    )
    with engine.begin() as conn:
        # (1) par saudável
        conn.execute(sa.text("CREATE TABLE lote (id serial PRIMARY KEY, fazenda_id int NOT NULL, nome text)"))
        conn.execute(sa.text(
            "CREATE TABLE animal (id serial PRIMARY KEY, fazenda_id int NOT NULL, "
            "lote_id int REFERENCES lote(id), numero text)"
        ))
        conn.execute(sa.text("INSERT INTO lote (id, fazenda_id, nome) VALUES (10, 1, 'lote da fazenda 1')"))
        conn.execute(sa.text("INSERT INTO animal (fazenda_id, lote_id, numero) VALUES (1, 10, 'vaca saudavel')"))

        # (2) referência cruzada: fazenda 2 aponta pro lote da fazenda 1
        conn.execute(sa.text(
            "CREATE TABLE servico (id serial PRIMARY KEY, fazenda_id int NOT NULL, "
            "lote_id int REFERENCES lote(id), tipo text)"
        ))
        conn.execute(sa.text(
            "INSERT INTO servico (fazenda_id, lote_id, tipo) VALUES (2, 10, 'vacinacao cruzada')"
        ))

        # (3) catálogo global — fazenda_id nulo de propósito, não pode compor
        conn.execute(sa.text("CREATE TABLE principio_ativo (id serial PRIMARY KEY, fazenda_id int, nome text)"))
        conn.execute(sa.text(
            "CREATE TABLE receita (id serial PRIMARY KEY, fazenda_id int NOT NULL, "
            "principio_ativo_id int REFERENCES principio_ativo(id))"
        ))
        conn.execute(sa.text("INSERT INTO principio_ativo (id, fazenda_id, nome) VALUES (99, NULL, 'ocitocina')"))
        conn.execute(sa.text("INSERT INTO receita (fazenda_id, principio_ativo_id) VALUES (1, 99)"))

        # (4) auto-referência
        conn.execute(sa.text(
            "CREATE TABLE categoria (id serial PRIMARY KEY, fazenda_id int NOT NULL, "
            "categoria_pai_id int REFERENCES categoria(id), nome text)"
        ))
        conn.execute(sa.text("INSERT INTO categoria (id, fazenda_id, nome) VALUES (1, 1, 'raiz')"))
        conn.execute(sa.text("SELECT setval('categoria_id_seq', 1)"))
        conn.execute(sa.text(
            "INSERT INTO categoria (fazenda_id, categoria_pai_id, nome) VALUES (1, 1, 'filha')"
        ))

    yield engine

    engine.dispose()
    admin = sa.create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
    admin.dispose()


def _fk_de(conn, tabela: str) -> str:
    return conn.execute(sa.text(
        f"SELECT conname FROM pg_constraint WHERE conrelid = '{tabela}'::regclass AND contype = 'f' "
        "AND array_length(conkey, 1) > 0 ORDER BY conname LIMIT 1"
    )).scalar()


def _e_composta(conn, tabela: str, nome_constraint: str) -> bool:
    cols = conn.execute(sa.text(
        "SELECT array_agg(att.attname) FROM pg_constraint con "
        "JOIN unnest(con.conkey) AS k(attnum) ON true "
        "JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.attnum "
        f"WHERE con.conname = '{nome_constraint}' AND con.conrelid = '{tabela}'::regclass"
    )).scalar()
    return "fazenda_id" in (cols or [])


def test_par_saudavel_vira_composta(banco):
    """O caso comum: a filha sempre apontou pro pai da própria fazenda —
    compor não tem o que recusar."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()

        nome = _fk_de(conn, "animal")
        assert _e_composta(conn, "animal", nome), "animal->lote tinha que virar composta"

        unique = conn.execute(sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'uq_lote_id_fazenda_id'"
        )).first()
        assert unique, "UNIQUE(id, fazenda_id) tinha que ter sido criada em lote"


def test_referencia_cruzada_e_pulada_sem_derrubar_as_outras(banco):
    """O teste que mais importa: uma violação real (fazenda 2 usando lote da
    fazenda 1) não pode abortar a migração, e a tabela não pode ficar SEM
    NENHUMA FK — tem que voltar pra simples, exatamente como estava."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()  # se levantar, o teste falha aqui e é esse o ponto

        nome = _fk_de(conn, "servico")
        assert nome == "servico_lote_id_fkey", (
            "a FK pulada tinha que continuar com o nome ORIGINAL simples, não sumir"
        )
        assert not _e_composta(conn, "servico", nome), (
            "pulada quer dizer simples — nunca sem nenhuma FK"
        )

        # a violação em si continua gravada — a migração não apaga dado
        linha = conn.execute(sa.text("SELECT fazenda_id, lote_id FROM servico")).first()
        assert linha == (2, 10)

        # e a tabela saudável (animal) foi composta mesmo assim — uma
        # violação numa tabela não pode impedir as demais
        nome_animal = _fk_de(conn, "animal")
        assert _e_composta(conn, "animal", nome_animal)


def test_catalogo_global_continua_simples(banco):
    """`principio_ativo` tem `fazenda_id` NULO de propósito — compor
    quebraria o compartilhamento (achado 1, fks-compostas.md)."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()

        nome = _fk_de(conn, "receita")
        assert not _e_composta(conn, "receita", nome), (
            "FK pro catalogo global tem que continuar simples"
        )
        unique = conn.execute(sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'uq_principio_ativo_id_fazenda_id'"
        )).first()
        assert not unique, "catalogo global nao ganha UNIQUE(id, fazenda_id)"


def test_auto_referencia_funciona(banco):
    """A UNIQUE de `categoria` precisa existir ANTES da própria FK de
    `categoria` poder usá-la — mesma tabela dos dois lados."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()

        nome = _fk_de(conn, "categoria")
        assert _e_composta(conn, "categoria", nome)

        # continua aceitando gravar
        conn.execute(sa.text(
            "INSERT INTO categoria (fazenda_id, categoria_pai_id, nome) VALUES (1, 1, 'outra filha')"
        ))


def test_downgrade_devolve_ao_estado_original(banco):
    """O downgrade reverte só o que ESTÁ composto hoje — apurado no banco,
    não uma lista fixa (roda num processo separado do upgrade)."""
    mig = _modulo()
    with banco.begin() as conn:
        mig.op = _Op(conn)
        mig.upgrade()
        mig.downgrade()

        nome_animal = _fk_de(conn, "animal")
        assert not _e_composta(conn, "animal", nome_animal), "downgrade tinha que devolver a FK simples"

        unique = conn.execute(sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'uq_lote_id_fazenda_id'"
        )).first()
        assert not unique, "downgrade tinha que ter removido a UNIQUE"

        # o dado da referência cruzada — que nunca foi composta — não foi
        # tocado pelo downgrade (nada a reverter ali)
        linha = conn.execute(sa.text("SELECT fazenda_id, lote_id FROM servico")).first()
        assert linha == (2, 10)
