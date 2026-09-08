"""
Migração d4a17c60be92 — `pessoa.vale_alimentacao_forma` e
`pessoa.vale_alimentacao_natureza_travada_salarial`.

POR QUE ESTA MIGRAÇÃO PRECISA DE TESTE PRÓPRIO. `database.py::_aplicar_alembic`
roda `command.upgrade(cfg, "head")` NO BOOT da API: migração que aborta é API
que não sobe. E ela sobe junto com `SQLModel.metadata.create_all`, então em
deploy as colunas novas podem JÁ EXISTIR quando o upgrade roda — um
`add_column` cru abortaria o upgrade INTEIRO. Daí a idempotência com
`sa.inspect`, no padrão de b7d21f9c4a30 e c3e91b47da28, e daí este arquivo.

O QUE ESTES TESTES TRAVAM:
 - as duas colunas passam a existir, NULLABLE e sem `server_default` (nada de
   reescrita de tabela grande no boot de uma API que precisa subir);
 - o funcionário que JÁ tinha o vale-alimentação ligado fica com forma NULL e
   trava NULL — nenhum backfill, e a ausência é decisão: carimbar "cartao" em
   quem já estava configurado reproduziria em dados a suposição que esta
   migração existe para desfazer, e o holerite sairia dizendo "sem incidência
   de INSS, IRRF e FGTS" com a autoridade de um dado gravado. NULL faz a regra
   enquadrar como salarial (o lado que não subdeclara base) até alguém abrir o
   cadastro e escolher — ver `vale_alimentacao.natureza_do_vale_alimentacao`;
 - rodar o upgrade com as colunas já criadas (o cenário do deploy) NÃO aborta;
 - o downgrade remove as duas e o resto da configuração do vale-alimentação
   (valor, periodicidade, regime) sobrevive à ida e à volta.

Mesma técnica de subprocesso das demais migrações (ver
test_migracao_vale_natureza_assuncao.py).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REVISAO_ANTERIOR = "c3e91b47da28"
REVISAO = "d4a17c60be92"
COLUNAS_NOVAS = {"vale_alimentacao_forma", "vale_alimentacao_natureza_travada_salarial"}


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
    db_path = tmp_path / "vale_alimentacao_natureza.db"
    _rodar_alembic(db_path, "upgrade", REVISAO_ANTERIOR)
    return db_path


def _executar(db_path: Path, sql: str, parametros: tuple = ()) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(sql, parametros)
    conn.commit()
    conn.close()


def _colunas(db_path: Path, tabela: str = "pessoa") -> dict[str, dict]:
    conn = sqlite3.connect(db_path)
    info = {
        c[1]: {"tipo": c[2], "notnull": c[3], "default": c[4]}
        for c in conn.execute(f"PRAGMA table_info({tabela})")
    }
    conn.close()
    return info


def _pessoa_com_va_antigo(db_path: Path) -> int:
    """Um funcionário com o vale-alimentação JÁ configurado antes de existir a
    forma de pagamento — é exatamente o registro que está no banco de quem
    adotou o cadastro entre c3e91b47da28 e esta migração, e o que nenhuma
    coluna nova tem como descrever retroativamente."""
    _executar(
        db_path,
        "INSERT INTO pessoa "
        "(nome, tipo, ativo, criado_em, salario_base, vale_alimentacao, vale_alimentacao_valor, "
        " vale_alimentacao_periodicidade, vale_alimentacao_regime) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Leomir Bonfim", "Funcionário", 1, "2026-01-05 10:00:00", 3200.0, 1, 25.0,
         "diario", "vencido"),
    )
    return 1


class TestColunasNovas:
    def test_as_duas_colunas_passam_a_existir_nullable_e_sem_default(self, banco_pre_migracao):
        """Nullable e sem `server_default` de propósito: o upgrade roda no boot
        da API e um default obrigaria o Postgres a reescrever `pessoa` inteira
        antes de a API subir. E NULL é a informação certa para o passado —
        ninguém sabe em que forma a fazenda vinha pagando o benefício antes de
        o campo existir."""
        assert COLUNAS_NOVAS.isdisjoint(_colunas(banco_pre_migracao))
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        colunas = _colunas(banco_pre_migracao)
        assert COLUNAS_NOVAS <= set(colunas)
        for nome in COLUNAS_NOVAS:
            assert colunas[nome]["notnull"] == 0, f"{nome} tem de aceitar NULL"
            assert colunas[nome]["default"] is None, f"{nome} não pode ter server_default"

    def test_quem_ja_tinha_o_beneficio_fica_sem_forma_e_sem_trava(self, banco_pre_migracao):
        """O backfill que esta migração NÃO faz — e não pode fazer. Carimbar
        "cartao" seria gravar a suposição que a migração existe para desfazer, e
        um holerite passaria a afirmar "sem incidência de INSS, IRRF e FGTS" com
        a autoridade de um dado, não de um chute. NULL mantém o funcionário no
        enquadramento salarial (o lado que não subdeclara base) até alguém
        escolher a forma no cadastro."""
        _pessoa_com_va_antigo(banco_pre_migracao)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        forma, travada, ligado, valor, periodicidade, regime = conn.execute(
            "SELECT vale_alimentacao_forma, vale_alimentacao_natureza_travada_salarial, "
            "       vale_alimentacao, vale_alimentacao_valor, vale_alimentacao_periodicidade, "
            "       vale_alimentacao_regime "
            "FROM pessoa WHERE id = 1"
        ).fetchone()
        conn.close()
        assert forma is None and travada is None
        # E nada do que já estava configurado foi tocado.
        assert (ligado, valor, periodicidade, regime) == (1, 25.0, "diario", "vencido")

    def test_ninguem_ganha_vale_alimentacao_por_causa_da_migracao(self, banco_pre_migracao):
        """A contraprova do lado de fora: quem nunca teve o benefício continua
        sem ele — as colunas novas não ligam nada."""
        _executar(
            banco_pre_migracao,
            "INSERT INTO pessoa (nome, tipo, ativo, criado_em) VALUES (?, ?, ?, ?)",
            ("Valéria Souza", "Funcionário", 1, "2026-01-05 10:00:00"),
        )
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        ligado, forma = conn.execute(
            "SELECT vale_alimentacao, vale_alimentacao_forma FROM pessoa WHERE id = 1"
        ).fetchone()
        conn.close()
        assert not ligado and forma is None


class TestIdempotencia:
    def test_upgrade_nao_aborta_com_as_colunas_ja_criadas(self, banco_pre_migracao):
        """O CENÁRIO DO DEPLOY: a app sobe e `SQLModel.metadata.create_all`
        cria as colunas novas antes de o `alembic upgrade head` terminar. Um
        `add_column` cru abortaria o upgrade INTEIRO aqui — e a API não subiria
        mais. Por isso a migração pergunta antes (`sa.inspect`)."""
        _pessoa_com_va_antigo(banco_pre_migracao)
        _executar(banco_pre_migracao, "ALTER TABLE pessoa ADD COLUMN vale_alimentacao_forma VARCHAR")
        _executar(
            banco_pre_migracao,
            "ALTER TABLE pessoa ADD COLUMN vale_alimentacao_natureza_travada_salarial BOOLEAN",
        )

        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        assert COLUNAS_NOVAS <= set(_colunas(banco_pre_migracao))
        # `alembic current` mostra a revisão CORRENTE, que é a cabeça do
        # projeto — não necessariamente esta. O que se prova aqui é que o
        # upgrade CHEGOU AO FIM com as colunas já criadas, ou seja, que esta
        # revisão ficou aplicada; comparar com "a última do projeto" quebraria
        # de novo na próxima migração que entrasse.
        aplicadas = _rodar_alembic(banco_pre_migracao, "history", "-r", "base:current")
        assert REVISAO in aplicadas, f"a revisão tinha de ficar aplicada. Aplicadas: {aplicadas}"


class TestDowngrade:
    def test_downgrade_remove_as_duas_colunas_e_o_cadastro_sobrevive(self, banco_pre_migracao):
        _pessoa_com_va_antigo(banco_pre_migracao)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        _executar(
            banco_pre_migracao,
            "UPDATE pessoa SET vale_alimentacao_forma = 'dinheiro', "
            "vale_alimentacao_natureza_travada_salarial = 1 WHERE id = 1",
        )
        _rodar_alembic(banco_pre_migracao, "downgrade", REVISAO_ANTERIOR)

        colunas = _colunas(banco_pre_migracao)
        assert COLUNAS_NOVAS.isdisjoint(colunas)
        conn = sqlite3.connect(banco_pre_migracao)
        ligado, valor, periodicidade, regime = conn.execute(
            "SELECT vale_alimentacao, vale_alimentacao_valor, vale_alimentacao_periodicidade, "
            "       vale_alimentacao_regime FROM pessoa WHERE id = 1"
        ).fetchone()
        conn.close()
        assert (ligado, valor, periodicidade, regime) == (1, 25.0, "diario", "vencido")

    def test_upgrade_de_novo_depois_do_downgrade_volta_com_as_colunas_vazias(self, banco_pre_migracao):
        """A forma gravada NÃO volta do downgrade — a coluna foi apagada, o
        dado foi junto. O funcionário reaparece como "forma desconhecida", que
        é o único estado honesto depois de um ida-e-volta assim, e é o estado
        que a regra enquadra como salarial em vez de adivinhar um PAT."""
        _pessoa_com_va_antigo(banco_pre_migracao)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        _executar(
            banco_pre_migracao,
            "UPDATE pessoa SET vale_alimentacao_forma = 'cartao' WHERE id = 1",
        )
        _rodar_alembic(banco_pre_migracao, "downgrade", REVISAO_ANTERIOR)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        forma, travada, valor = conn.execute(
            "SELECT vale_alimentacao_forma, vale_alimentacao_natureza_travada_salarial, "
            "       vale_alimentacao_valor FROM pessoa WHERE id = 1"
        ).fetchone()
        conn.close()
        assert forma is None and travada is None
        # O que a migração nunca tocou continua intacto depois da ida e volta.
        assert valor == 25.0
