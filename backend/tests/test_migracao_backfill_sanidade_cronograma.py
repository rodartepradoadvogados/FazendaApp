"""
Migração aa88749c85b0 (backfill de fazenda_id órfão em sanidade/
cronograma_sanitario_animal via animal.numero) — ver a docstring da própria
migração para o raciocínio completo (por que `numero_matriz -> animal.numero
-> animal.fazenda_id` é inequívoco nesta migração especificamente, mesmo
com 2+ fazendas reais cadastradas).

Mesma técnica de tests/test_migracao_fazenda_id_backfill.py: roda o
`alembic upgrade` de verdade, em subprocesso, contra um SQLite descartável
— não dá pra chamar a migração como função Python direto porque
`alembic/env.py` lê `DATABASE_URL` fixado no import de `fazenda.database`.

Sobe só até a PRÓPRIA migração (não até head): a migração seguinte
(c24befa94c1b) troca a unicidade de `animal.numero` para (fazenda_id,
numero) e barra qualquer duplicata de numero na mesma fazenda — o cenário
de teste aqui usa números repetidos entre FAZENDA_A/FAZENDA_B de propósito
(é exatamente o que a análise de ambiguidade depende), então rodar até head
faria essa migração seguinte falhar por motivo errado (checagem dela, não
desta).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

FAZENDA_A = 900
FAZENDA_B = 901


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


def _inserir_fazenda(conn: sqlite3.Connection, id_: int, nome: str) -> None:
    conn.execute(
        "INSERT INTO fazenda (id, nome, ativa, criado_em, eh_empresa_cowdata) VALUES (?, ?, 1, CURRENT_TIMESTAMP, 0)",
        (id_, nome),
    )


def _inserir_animal(conn: sqlite3.Connection, id_: int, numero: str, fazenda_id: int) -> None:
    conn.execute(
        "INSERT INTO animal (id, numero, eh_semen, ativo, atualizado_em, grupo_manual, a_descartar, "
        "excluir_bst, fazenda_id) VALUES (?, ?, 0, 1, CURRENT_TIMESTAMP, 0, 0, 0, ?)",
        (id_, numero, fazenda_id),
    )


def _inserir_sanidade(conn: sqlite3.Connection, id_: int, numero_matriz: str) -> None:
    """fazenda_id NULO de propósito — é o que a migração precisa preencher."""
    conn.execute(
        "INSERT INTO sanidade (id, numero_matriz, produto, atualizado_em, fazenda_id) "
        "VALUES (?, ?, 'Vacina X', CURRENT_TIMESTAMP, NULL)",
        (id_, numero_matriz),
    )


def _inserir_cronograma_chain(conn: sqlite3.Connection, fazenda_id_cronograma) -> int:
    """Cria a cadeia evento_sanitario -> calendario_sanitario ->
    cronograma_sanitario mínima pra sustentar um CronogramaSanitarioAnimal.
    Devolve o id do cronograma_sanitario criado (sempre 1, banco novo)."""
    conn.execute(
        "INSERT INTO evento_sanitario (id, nome, ativo, tipo_agendamento, criado_em) "
        "VALUES (1, 'Vacina X', 1, 'fixo', CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO calendario_sanitario (id, evento_sanitario_id, frequencia_valor, frequencia_unidade, "
        "data_evento, ativo, criado_em) VALUES (1, 1, 1, 'dias', '2026-08-01', 1, CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO cronograma_sanitario (id, calendario_sanitario_id, data_evento, status, criado_em, "
        "atualizado_em, fazenda_id) VALUES (1, 1, '2026-08-01', 'aberto', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)",
        (fazenda_id_cronograma,),
    )
    return 1


def _inserir_cronograma_animal(conn: sqlite3.Connection, id_: int, cronograma_id: int, numero_matriz: str) -> None:
    """fazenda_id NULO de propósito."""
    conn.execute(
        "INSERT INTO cronograma_sanitario_animal (id, cronograma_id, numero_matriz, status, data_sugestao, "
        "fazenda_id) VALUES (?, ?, ?, 'sugerido', '2026-08-01', NULL)",
        (id_, cronograma_id, numero_matriz),
    )


@pytest.fixture
def banco_pre_migracao(tmp_path):
    """Sobe o schema até a migração ANTERIOR a esta (a1c3e7f0b2d4, head do
    repo antes desta "fundação") — sem o backfill — pra este teste popular
    os dados órfãos manualmente antes de rodar a migração de verdade."""
    db_path = tmp_path / "backfill_sanidade.db"
    _rodar_alembic(db_path, "upgrade", "a1c3e7f0b2d4")
    return db_path


class TestSanidadeRecuperaViaAnimal:
    def test_recupera_fazenda_da_matriz_com_duas_fazendas_reais(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_fazenda(conn, FAZENDA_A, "Fazenda A")
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda B")
        _inserir_animal(conn, 1, "500", FAZENDA_B)
        _inserir_sanidade(conn, 1, "500")
        conn.commit()
        conn.close()

        _rodar_alembic(banco_pre_migracao, "upgrade", "aa88749c85b0")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM sanidade WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id == FAZENDA_B, "deveria ter herdado a fazenda do animal casado pelo numero_matriz"

    def test_numero_matriz_sem_animal_correspondente_fica_nulo(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_fazenda(conn, FAZENDA_A, "Fazenda A")
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda B")
        _inserir_sanidade(conn, 1, "numero-inexistente")
        conn.commit()
        conn.close()

        saida = _rodar_alembic(banco_pre_migracao, "upgrade", "aa88749c85b0")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM sanidade WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id is None, "não deveria adivinhar quando o numero_matriz não casa com nenhum animal"
        assert "AINDA NULO: 1" in saida


class TestCronogramaAnimalRecuperaViaPaiOuAnimal:
    def test_deriva_do_cronograma_pai_quando_pai_ja_tem_fazenda(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_fazenda(conn, FAZENDA_A, "Fazenda A")
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda B")
        cronograma_id = _inserir_cronograma_chain(conn, FAZENDA_B)
        # numero_matriz nem precisa casar com nenhum animal — a derivação
        # pelo PAI vem antes e já resolve sozinha.
        _inserir_cronograma_animal(conn, 1, cronograma_id, "numero-qualquer")
        conn.commit()
        conn.close()

        _rodar_alembic(banco_pre_migracao, "upgrade", "aa88749c85b0")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM cronograma_sanitario_animal WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id == FAZENDA_B

    def test_cai_para_animal_quando_cronograma_pai_tambem_esta_nulo(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_fazenda(conn, FAZENDA_A, "Fazenda A")
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda B")
        cronograma_id = _inserir_cronograma_chain(conn, None)  # pai também órfão
        _inserir_animal(conn, 1, "700", FAZENDA_A)
        _inserir_cronograma_animal(conn, 1, cronograma_id, "700")
        conn.commit()
        conn.close()

        _rodar_alembic(banco_pre_migracao, "upgrade", "aa88749c85b0")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM cronograma_sanitario_animal WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id == FAZENDA_A, "sem pai pra derivar, deveria ter caído para numero_matriz->animal"

    def test_sem_pai_e_sem_animal_correspondente_fica_nulo(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_fazenda(conn, FAZENDA_A, "Fazenda A")
        _inserir_fazenda(conn, FAZENDA_B, "Fazenda B")
        cronograma_id = _inserir_cronograma_chain(conn, None)
        _inserir_cronograma_animal(conn, 1, cronograma_id, "numero-inexistente")
        conn.commit()
        conn.close()

        saida = _rodar_alembic(banco_pre_migracao, "upgrade", "aa88749c85b0")

        conn = sqlite3.connect(banco_pre_migracao)
        fazenda_id = conn.execute("SELECT fazenda_id FROM cronograma_sanitario_animal WHERE id = 1").fetchone()[0]
        conn.close()
        assert fazenda_id is None
        assert "cronograma_sanitario_animal" in saida
