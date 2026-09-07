"""
Migração a4f8c1d92e07 — o backfill dos órfãos que a 029227481e9e deixou.

Testa a LÓGICA de decisão da migração sem precisar de PostgreSQL: importa o
módulo da revisão e exercita `_fazenda_cliente_unica` e as três listas de
tabelas contra um SQLite montado para o caso.

O que estes testes protegem, em ordem de importância:

1. **A migração não chuta o dono de um registro.** Se não houver EXATAMENTE
   uma fazenda-cliente, ela não faz nada. É a mesma recusa da 029227481e9e, e
   a razão é a mesma: num banco multi-tenant, atribuir por chute cria um
   vazamento com aparência de conserto.

2. **`eh_teste` conta.** Foi justamente ignorá-la que fez a 029227481e9e ver
   "duas fazendas" onde só há uma cliente, desistir, e deixar os órfãos
   parados. Se alguém reverter esse filtro, o teste fica vermelho.

3. **O catálogo global não é tocado.** `medicamento_categoria` e
   `medicamento_classificacao` não podem aparecer em nenhuma das listas: o
   NULL nelas espelha o NULL do medicamento-pai global, e atribuí-lo faria o
   vínculo "pertencer" a uma fazenda e sumir do catálogo de todas as outras
   (o próprio modelo avisa isso).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

_ARQUIVO = (
    Path(__file__).resolve().parent.parent
    / "alembic" / "versions" / "a4f8c1d92e07_backfill_orfaos_restantes.py"
)


def _modulo():
    spec = importlib.util.spec_from_file_location("mig_backfill_orfaos", _ARQUIVO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mig():
    return _modulo()


def _banco(linhas: list[tuple[int, bool, bool]]):
    """SQLite com a tabela `fazenda` mínima. Cada linha: (id, cowdata, teste)."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE fazenda (id INTEGER PRIMARY KEY, nome TEXT, "
            "eh_empresa_cowdata BOOLEAN, eh_teste BOOLEAN)"
        ))
        for fid, cowdata, teste in linhas:
            conn.execute(
                text("INSERT INTO fazenda VALUES (:i, :n, :c, :t)"),
                {"i": fid, "n": f"f{fid}", "c": cowdata, "t": teste},
            )
    return engine


def test_producao_hoje_resolve_a_fazenda_cliente_unica(mig):
    """O cenário real, medido em 06/09/2026: Jairo Nasser (cliente), Fazenda
    Teste (sandbox) e CowData (painel). Tem que resolver a 1."""
    engine = _banco([(1, False, False), (2, False, True), (3, True, False)])
    with engine.connect() as conn:
        assert mig._fazenda_cliente_unica(conn) == 1


def test_a_sandbox_nao_conta_como_cliente(mig):
    """O defeito da 029227481e9e, travado aqui.

    Sem descontar `eh_teste`, este cenário tem "duas fazendas" e a migração
    desistiria — que foi exatamente o que aconteceu e deixou os órfãos
    parados desde julho.
    """
    engine = _banco([(1, False, False), (2, False, True)])
    with engine.connect() as conn:
        assert mig._fazenda_cliente_unica(conn) == 1


def test_duas_fazendas_cliente_de_verdade_nao_adivinha(mig):
    """A recusa que importa: com dois clientes reais, não há como saber de
    quem é o órfão, e a migração não inventa."""
    engine = _banco([(1, False, False), (2, False, False), (3, True, False)])
    with engine.connect() as conn:
        assert mig._fazenda_cliente_unica(conn) is None


def test_sem_fazenda_cliente_nenhuma_nao_faz_nada(mig):
    """Só o painel e a sandbox — nenhum cliente. Nada a atribuir."""
    engine = _banco([(2, False, True), (3, True, False)])
    with engine.connect() as conn:
        assert mig._fazenda_cliente_unica(conn) is None


def test_banco_sem_a_coluna_eh_teste_nao_quebra(mig):
    """Banco anterior à flag: o filtro extra é omitido em vez de dar erro de
    coluna inexistente."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE fazenda (id INTEGER PRIMARY KEY, nome TEXT, eh_empresa_cowdata BOOLEAN)"
        ))
        conn.execute(text("INSERT INTO fazenda VALUES (1, 'f1', 0)"))
    with engine.connect() as conn:
        assert mig._fazenda_cliente_unica(conn) == 1


def test_catalogo_global_nunca_entra_nas_listas(mig):
    """`medicamento_categoria` e `medicamento_classificacao` têm NULL
    legítimo — espelham o NULL do medicamento-pai global. Atribuir faria o
    vínculo sumir do catálogo de todas as outras fazendas."""
    todas = set(mig._ATRIBUIR) | set(mig._APAGAR_RESIDUO_DE_MIGRACAO) | set(mig._APAGAR_LIXO_TECNICO)
    for tabela in ("medicamento_categoria", "medicamento_classificacao",
                   "principio_ativo", "doenca", "medicamento_comercial",
                   "alimento_nutricional", "medicamento_principio_ativo"):
        assert tabela not in todas, f"{tabela} é catálogo global e não pode ser tocada"


def test_nenhuma_tabela_aparece_em_duas_listas(mig):
    """Atribuir e apagar a mesma tabela seria contraditório — e o resultado
    dependeria da ordem, que é o pior tipo de bug de migração."""
    listas = {
        "atribuir": mig._ATRIBUIR,
        "residuo": mig._APAGAR_RESIDUO_DE_MIGRACAO,
        "lixo": mig._APAGAR_LIXO_TECNICO,
    }
    vistas: dict[str, str] = {}
    for nome, tabelas in listas.items():
        for t in tabelas:
            assert t not in vistas, f"{t} está em '{vistas.get(t)}' e em '{nome}'"
            vistas[t] = nome


def test_calendario_vem_antes_do_cronograma(mig):
    """O cronograma é filho do calendário e a órfã dele é a única linha da
    tabela: as duas são o mesmo evento e têm que acabar na mesma fazenda."""
    ordem = mig._ATRIBUIR
    assert ordem.index("calendario_sanitario") < ordem.index("cronograma_sanitario")


def test_as_com_nome_unico_sao_subconjunto_das_atribuidas(mig):
    """A limpeza de duplicata por nome só faz sentido para tabela que vai ser
    atribuída — numa que será apagada, ela seria trabalho perdido."""
    assert set(mig._COM_NOME_UNICO) <= set(mig._ATRIBUIR)


def test_o_sql_de_duplicata_roda_em_sqlite(mig):
    """Regressão de um bug real desta migração, pego pela suíte.

    A primeira versão escrevia `DELETE FROM tabela o WHERE o.fazenda_id ...`.
    O PostgreSQL aceita o alias; o SQLite recusa com "near o: syntax error" —
    e a suíte aplica as migrações em SQLite (database.py::create_db_and_tables),
    então a migração derrubava a suíte inteira. Os testes de lógica acima não
    pegaram porque nenhum deles EXECUTA o SQL.

    Este executa: monta a tabela com uma linha da fazenda e uma órfã de mesmo
    nome, roda o comando que a migração roda, e confere que só a órfã sai.
    """
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE tipo_documento (id INTEGER PRIMARY KEY, nome TEXT, fazenda_id INTEGER)"
        ))
        conn.execute(text(
            "INSERT INTO tipo_documento (id, nome, fazenda_id) VALUES "
            "(1, 'Nota Fiscal', 1), (2, 'Nota Fiscal', NULL), (3, 'Recibo', NULL)"
        ))
        apagadas = conn.execute(
            text(
                "DELETE FROM tipo_documento WHERE fazenda_id IS NULL"
                "  AND lower(trim(nome)) IN ("
                "    SELECT lower(trim(nome)) FROM tipo_documento WHERE fazenda_id = :fid)"
            ),
            {"fid": 1},
        ).rowcount
        assert apagadas == 1, "só a órfã duplicada devia sair"
        restantes = [
            (r[1], r[2]) for r in conn.execute(
                text("SELECT id, nome, fazenda_id FROM tipo_documento ORDER BY id")
            )
        ]
    assert restantes == [("Nota Fiscal", 1), ("Recibo", None)], (
        "a linha da fazenda tinha que ficar, e a órfã sem duplicata também"
    )


# ---------------------------------------------------------------------------
# O ciclo completo: upgrade e volta. É a garantia de regressão que o dono
# pediu antes de autorizar o merge, e ela só vale se for exercitada.
# ---------------------------------------------------------------------------

_ESQUEMA_MINIMO = [
    "CREATE TABLE fazenda (id INTEGER PRIMARY KEY, nome TEXT,"
    " eh_empresa_cowdata BOOLEAN, eh_teste BOOLEAN)",
    "CREATE TABLE tipo_documento (id INTEGER PRIMARY KEY, nome TEXT, fazenda_id INTEGER)",
    "CREATE TABLE conta_gerencial (id INTEGER PRIMARY KEY, descricao TEXT, fazenda_id INTEGER)",
    "CREATE TABLE calendario_sanitario (id INTEGER PRIMARY KEY, titulo TEXT, fazenda_id INTEGER)",
    "CREATE TABLE cronograma_sanitario (id INTEGER PRIMARY KEY, calendario_id INTEGER,"
    " fazenda_id INTEGER, FOREIGN KEY (calendario_id) REFERENCES calendario_sanitario (id))",
    "CREATE TABLE meta_recria (id INTEGER PRIMARY KEY, valor INTEGER, fazenda_id INTEGER)",
    "CREATE TABLE idempotencia_chave (id INTEGER PRIMARY KEY, chave TEXT, fazenda_id INTEGER)",
]

_DADO_INICIAL = [
    # as 3 fazendas de produção: a real, a sandbox e a da própria CowData
    "INSERT INTO fazenda VALUES (1, 'Jairo Nasser', 0, 0), (2, 'Teste', 0, 1), (3, 'CowData', 1, 0)",
    # nome único: a órfã 'Nota Fiscal' colide com a da fazenda; 'Recibo' não
    "INSERT INTO tipo_documento VALUES (1, 'Nota Fiscal', 1), (2, 'Nota Fiscal', NULL),"
    " (3, 'Recibo', NULL)",
    "INSERT INTO conta_gerencial VALUES (1, 'Custeio', NULL)",
    "INSERT INTO calendario_sanitario VALUES (1, 'Vacinação', NULL)",
    "INSERT INTO cronograma_sanitario VALUES (1, 1, NULL)",
    # resíduo: a fazenda já tem a dela, a órfã é a linha antiga
    "INSERT INTO meta_recria VALUES (1, 100, NULL), (2, 200, 1)",
    "INSERT INTO idempotencia_chave VALUES (1, 'abc', NULL)",
]

_TABELAS_DE_DADO = [
    "tipo_documento", "conta_gerencial", "calendario_sanitario",
    "cronograma_sanitario", "meta_recria", "idempotencia_chave",
]


def _retrato(conn) -> dict:
    """Estado de todas as tabelas de dado, para comparar antes e depois."""
    retrato = {}
    for tabela in _TABELAS_DE_DADO:
        linhas = conn.execute(text(f"SELECT * FROM {tabela} ORDER BY id")).fetchall()
        retrato[tabela] = [tuple(linha) for linha in linhas]
    return retrato


def _banco_de_producao():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for comando in _ESQUEMA_MINIMO + _DADO_INICIAL:
            conn.execute(text(comando))
    return engine


class _OpFalso:
    """`op.get_bind()` fora do Alembic: devolve a conexão do teste."""

    def __init__(self, conn):
        self._conn = conn

    def get_bind(self):
        return self._conn


def test_ciclo_completo_upgrade_e_downgrade(mig):
    """Roda a migração de verdade e desfaz de verdade: o banco tem que voltar
    ao estado exato de antes, linha por linha.

    É a única prova de que o checkpoint que o dono pediu funciona. Sem ela, o
    `downgrade` seria só uma promessa escrita na docstring."""
    engine = _banco_de_producao()
    with engine.begin() as conn:
        mig.op = _OpFalso(conn)
        antes = _retrato(conn)

        mig.upgrade()
        depois = _retrato(conn)

        # a órfã duplicada de nome saiu; a outra foi atribuída
        assert depois["tipo_documento"] == [(1, "Nota Fiscal", 1), (3, "Recibo", 1)]
        # resíduo e cache: apagados
        assert depois["meta_recria"] == [(2, 200, 1)]
        assert depois["idempotencia_chave"] == []
        # dado real: atribuído, pai e filho na mesma fazenda
        assert depois["conta_gerencial"] == [(1, "Custeio", 1)]
        assert depois["calendario_sanitario"] == [(1, "Vacinação", 1)]
        assert depois["cronograma_sanitario"] == [(1, 1, 1)]

        mig.downgrade()
        voltou = _retrato(conn)

    assert voltou == antes, (
        "o downgrade tinha que devolver o banco ao estado exato de antes — "
        "é isso que torna o merge reversível"
    )


def test_o_checkpoint_guarda_as_orfas_antes_de_alterar(mig):
    """As tabelas de checkpoint têm que existir depois do upgrade, com a cópia
    das órfãs — é por elas que o downgrade volta."""
    engine = _banco_de_producao()
    with engine.begin() as conn:
        mig.op = _OpFalso(conn)
        mig.upgrade()

        nomes = {
            linha[0]
            for linha in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ckpt_%'")
            )
        }
        assert nomes == {f"{mig._CKPT}{t}" for t in _TABELAS_DE_DADO}

        # as três órfãs de tipo_documento (a duplicada inclusive) estão lá
        guardadas = conn.execute(
            text(f"SELECT id, nome FROM {mig._CKPT}tipo_documento ORDER BY id")
        ).fetchall()
        assert [tuple(linha) for linha in guardadas] == [(2, "Nota Fiscal"), (3, "Recibo")]


def test_tabela_sem_orfa_nao_ganha_checkpoint(mig):
    """Regressão da falha que a sentinela `test_migracao_tabelas_faltantes.py`
    pegou: num banco montado só pelo Alembic (ambiente novo, restauração), a
    fazenda vem semeada e não há órfã nenhuma — e a versão anterior criava as
    13 tabelas `ckpt_*` vazias assim mesmo, deixando no schema tabelas que
    nenhum model declara. Checkpoint vazio não é ponto de retorno de nada."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for comando in _ESQUEMA_MINIMO:
            conn.execute(text(comando))
        # uma fazenda-cliente única, e nenhuma órfã em tabela nenhuma
        conn.execute(text("INSERT INTO fazenda VALUES (1, 'Jairo Nasser', 0, 0)"))
        conn.execute(text("INSERT INTO tipo_documento VALUES (1, 'Nota Fiscal', 1)"))
        mig.op = _OpFalso(conn)

        mig.upgrade()

        criadas = [
            linha[0]
            for linha in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ckpt_%'")
            )
        ]
    assert criadas == [], "sem órfã não pode sobrar tabela de checkpoint no schema"


def test_reaplicar_o_upgrade_nao_destroi_o_checkpoint(mig):
    """A armadilha: depois da primeira passada não sobra órfã nenhuma. Se o
    upgrade recriasse o checkpoint, ele o substituiria por uma tabela VAZIA e
    o ponto de retorno sumiria — sem erro, em silêncio."""
    engine = _banco_de_producao()
    with engine.begin() as conn:
        mig.op = _OpFalso(conn)
        antes = _retrato(conn)

        mig.upgrade()
        mig.upgrade()  # reaplicação

        guardadas = conn.execute(
            text(f"SELECT count(*) FROM {mig._CKPT}tipo_documento")
        ).scalar()
        assert guardadas == 2, "o checkpoint da primeira passada tinha que ser preservado"

        mig.downgrade()
        assert _retrato(conn) == antes


def test_sem_fazenda_cliente_o_downgrade_nao_tem_o_que_desfazer(mig):
    """Num banco sem fazenda-cliente única (a suíte, por exemplo), o upgrade
    não altera nada e não cria checkpoint — o downgrade tem que ser inofensivo,
    não explodir por falta das tabelas `ckpt_*`."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for comando in _ESQUEMA_MINIMO + _DADO_INICIAL:
            conn.execute(text(comando))
        # duas fazendas-cliente: a migração se recusa a adivinhar
        conn.execute(text("INSERT INTO fazenda VALUES (4, 'Outra', 0, 0)"))
        mig.op = _OpFalso(conn)
        antes = _retrato(conn)

        mig.upgrade()
        assert _retrato(conn) == antes

        mig.downgrade()
        assert _retrato(conn) == antes
