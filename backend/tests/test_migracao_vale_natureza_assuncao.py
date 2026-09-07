"""
Migração b7d21f9c4a30 — `vale_parcela.natureza_assuncao` / `assuncao_detalhe`.

POR QUE ESTA MIGRAÇÃO PRECISA DE TESTE PRÓPRIO. `database.py::_aplicar_alembic`
roda `command.upgrade(cfg, "head")` NO BOOT da API: migração que aborta é API
que não sobe. E ela sobe junto com `SQLModel.metadata.create_all`, então em
deploy as colunas novas podem JÁ EXISTIR quando o upgrade roda — um
`add_column` cru abortaria o upgrade inteiro. Daí a idempotência com
`sa.inspect`, no mesmo padrão de a1c4e7b93f52, e daí este arquivo.

O QUE ESTES TESTES TRAVAM:
 - as duas colunas passam a existir, NULLABLE e sem `server_default` (nada de
   reescrita de tabela grande no boot);
 - parcela ANTIGA fica com NULL — "natureza desconhecida" —, e é isso que a
   mantém caindo na recusa por ambiguidade em `reverter_desconsideracao`:
   inventar natureza para o passado contaria a mesma despesa duas vezes;
 - rodar o upgrade com as colunas já criadas (o cenário do deploy) NÃO aborta;
 - o downgrade remove as duas e os dados da parcela sobrevivem à ida e volta.

Mesma técnica de subprocesso das demais migrações (ver
test_migracao_folha_discriminacao_congelada.py).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REVISAO_ANTERIOR = "a4f8c1d92e07"
REVISAO = "b7d21f9c4a30"
COLUNAS_NOVAS = {"natureza_assuncao", "assuncao_detalhe"}


def _rodar_alembic(db_path: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )
    assert resultado.returncode == 0, (
        f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{resultado.stdout}\nSTDERR:\n{resultado.stderr}"
    )
    return resultado.stdout


@pytest.fixture
def banco_pre_migracao(tmp_path):
    db_path = tmp_path / "vale_natureza.db"
    _rodar_alembic(db_path, "upgrade", REVISAO_ANTERIOR)
    return db_path


def _executar(db_path: Path, sql: str, parametros: tuple = ()) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(sql, parametros)
    conn.commit()
    conn.close()


def _colunas(db_path: Path, tabela: str = "vale_parcela") -> dict[str, dict]:
    conn = sqlite3.connect(db_path)
    info = {
        c[1]: {"tipo": c[2], "notnull": c[3], "default": c[4]}
        for c in conn.execute(f"PRAGMA table_info({tabela})")
    }
    conn.close()
    return info


def _parcela_antiga(db_path: Path) -> int:
    """Uma parcela ASSUMIDA gravada antes da migração — é o registro que já
    está no banco de produção hoje, e o que a coluna nova não tem como
    descrever retroativamente."""
    _executar(
        db_path,
        "INSERT INTO pessoa (nome, tipo, ativo, criado_em, salario_base) VALUES (?, ?, ?, ?, ?)",
        ("Leomir Bonfim", "Funcionário", 1, "2026-01-05 10:00:00", 3200.0),
    )
    _executar(
        db_path,
        "INSERT INTO vale_funcionario "
        "(pessoa_id, valor_total, forma_pagamento, data_pagamento, parcelas, competencia_inicio, "
        " criado_em, status, valor_abatido, valor_assumido_fazenda) "
        "VALUES (1, 900.0, 'pix', '2026-06-10', 3, '2026-07', '2026-06-10 10:00:00', 'ativo', 0, 300.0)",
    )
    _executar(
        db_path,
        "INSERT INTO vale_parcela "
        "(vale_id, pessoa_id, competencia, valor, aplicada, criado_em, assumida_pela_fazenda, motivo_assuncao) "
        "VALUES (1, 1, '2026-07', 300.0, 0, '2026-06-10 10:00:00', 1, 'trator')",
    )
    return 1


class TestColunasNovas:
    def test_as_duas_colunas_passam_a_existir_nullable_e_sem_default(self, banco_pre_migracao):
        """Nullable e sem `server_default` de propósito: o upgrade roda no boot
        da API e um default forçaria reescrever a tabela inteira; e NULL é a
        informação certa para o passado — "não sei o que a assunção fez"."""
        assert COLUNAS_NOVAS.isdisjoint(_colunas(banco_pre_migracao))
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        colunas = _colunas(banco_pre_migracao)
        assert COLUNAS_NOVAS <= set(colunas)
        for nome in COLUNAS_NOVAS:
            assert colunas[nome]["notnull"] == 0, f"{nome} tem de aceitar NULL"
            assert colunas[nome]["default"] is None, f"{nome} não pode ter server_default"

    def test_parcela_ja_assumida_fica_com_natureza_desconhecida(self, banco_pre_migracao):
        """O backfill que esta migração NÃO faz — e não pode fazer: não há de
        onde deduzir se aquela assunção soltou um item de nota ou não teve
        lastro nenhum. NULL mantém a parcela na recusa por ambiguidade, que é
        o comportamento correto."""
        _parcela_antiga(banco_pre_migracao)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        natureza, detalhe, assumida, motivo = conn.execute(
            "SELECT natureza_assuncao, assuncao_detalhe, assumida_pela_fazenda, motivo_assuncao "
            "FROM vale_parcela WHERE id = 1"
        ).fetchone()
        conn.close()
        assert natureza is None and detalhe is None
        # E nada do que já estava gravado foi tocado.
        assert assumida == 1 and motivo == "trator"


class TestIdempotencia:
    def test_upgrade_nao_aborta_com_as_colunas_ja_criadas(self, banco_pre_migracao):
        """O CENÁRIO DO DEPLOY: a app sobe e `SQLModel.metadata.create_all`
        cria as colunas novas antes de o `alembic upgrade head` terminar. Um
        `add_column` cru abortaria o upgrade INTEIRO aqui — e a API não subiria
        mais. Por isso a migração pergunta antes (`sa.inspect`)."""
        _parcela_antiga(banco_pre_migracao)
        _executar(banco_pre_migracao, "ALTER TABLE vale_parcela ADD COLUMN natureza_assuncao VARCHAR")
        _executar(banco_pre_migracao, "ALTER TABLE vale_parcela ADD COLUMN assuncao_detalhe VARCHAR")

        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        assert COLUNAS_NOVAS <= set(_colunas(banco_pre_migracao))
        # `alembic current` mostra a revisão CORRENTE, que é a cabeça do
        # projeto — não esta. A primeira versão deste teste comparava a saída
        # com REVISAO e passou a falhar assim que a migração seguinte entrou
        # (c3e91b47da28, do vale-alimentação): ele amarrava "a minha revisão"
        # a "a última do projeto", e quebraria de novo a cada migração nova.
        #
        # O que se quer provar aqui é que o upgrade CHEGOU ATÉ O FIM com as
        # colunas já criadas — ou seja, que esta revisão ficou aplicada, não
        # que ela é a última. `history -r` lista as revisões já aplicadas.
        aplicadas = _rodar_alembic(banco_pre_migracao, "history", "-r", "base:current")
        assert REVISAO in aplicadas, (
            f"a revisão tinha de ficar aplicada. Aplicadas: {aplicadas}"
        )


class TestDowngrade:
    def test_downgrade_remove_as_duas_colunas_e_a_parcela_sobrevive(self, banco_pre_migracao):
        _parcela_antiga(banco_pre_migracao)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        _executar(
            banco_pre_migracao,
            "UPDATE vale_parcela SET natureza_assuncao = 'sem_lastro', "
            "assuncao_detalhe = '{\"acao\": \"cancelar\"}' WHERE id = 1",
        )
        _rodar_alembic(banco_pre_migracao, "downgrade", REVISAO_ANTERIOR)

        colunas = _colunas(banco_pre_migracao)
        assert COLUNAS_NOVAS.isdisjoint(colunas)
        conn = sqlite3.connect(banco_pre_migracao)
        valor, assumida = conn.execute(
            "SELECT valor, assumida_pela_fazenda FROM vale_parcela WHERE id = 1"
        ).fetchone()
        conn.close()
        assert valor == 300.0 and assumida == 1

    def test_upgrade_de_novo_depois_do_downgrade_volta_com_as_colunas_vazias(self, banco_pre_migracao):
        """A natureza gravada NÃO volta do downgrade — a coluna foi apagada, o
        dado foi junto. O registro reaparece como "natureza desconhecida", que
        é o único estado honesto depois de um ida-e-volta assim."""
        _parcela_antiga(banco_pre_migracao)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        _executar(
            banco_pre_migracao,
            "UPDATE vale_parcela SET natureza_assuncao = 'lancamento_proprio' WHERE id = 1",
        )
        _rodar_alembic(banco_pre_migracao, "downgrade", REVISAO_ANTERIOR)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        natureza = conn.execute("SELECT natureza_assuncao FROM vale_parcela WHERE id = 1").fetchone()[0]
        conn.close()
        assert natureza is None
