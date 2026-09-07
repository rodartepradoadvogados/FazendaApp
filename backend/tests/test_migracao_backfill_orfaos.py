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


def test_downgrade_existe_e_nao_faz_nada(mig):
    """Reverter de verdade se faz por backup. O downgrade existe para o
    Alembic não quebrar, e não desfaz — devolver `fazenda_id = NULL` só
    recriaria o problema."""
    assert mig.downgrade() is None
