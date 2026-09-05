"""
Migração c24befa94c1b (animal.numero: unicidade global -> por fazenda) —
cobre as duas travas de segurança da própria migração, que preferem falhar
com mensagem clara a criar uma constraint que finge garantir o que não
garante (ver docstring da migração). Mesma técnica de subprocesso das
demais migrações desta "fundação" — ver test_migracao_fazenda_id_backfill.py.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


def _rodar_alembic(db_path: Path, *args: str):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )


def _inserir_animal(conn: sqlite3.Connection, id_: int, numero: str, fazenda_id) -> None:
    conn.execute(
        "INSERT INTO animal (id, numero, eh_semen, ativo, atualizado_em, grupo_manual, a_descartar, "
        "excluir_bst, fazenda_id) VALUES (?, ?, 0, 1, CURRENT_TIMESTAMP, 0, 0, 0, ?)",
        (id_, numero, fazenda_id),
    )


@pytest.fixture
def banco_pre_migracao(tmp_path):
    """Sobe até a migração ANTERIOR a esta (aa88749c85b0 — o backfill de
    sanidade/cronograma) e limpa a fazenda #1 semeada pelo piloto, pra este
    teste controlar sozinho quais animais/fazendas existem."""
    db_path = tmp_path / "unico_por_fazenda.db"
    resultado = _rodar_alembic(db_path, "upgrade", "aa88749c85b0")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM usuario_fazenda")
    conn.execute("DELETE FROM fazenda")
    conn.execute(
        "INSERT INTO fazenda (id, nome, ativa, criado_em, eh_empresa_cowdata) VALUES (1, 'Fazenda 1', 1, CURRENT_TIMESTAMP, 0)"
    )
    conn.execute(
        "INSERT INTO fazenda (id, nome, ativa, criado_em, eh_empresa_cowdata) VALUES (2, 'Fazenda 2', 1, CURRENT_TIMESTAMP, 0)"
    )
    conn.commit()
    conn.close()
    return db_path


class TestPermiteNumeroRepetidoEntreFazendas:
    def test_migra_com_sucesso_e_troca_a_constraint_pra_por_fazenda(self, banco_pre_migracao):
        # Pré-migração o índice antigo ainda é único GLOBAL — não dá pra
        # criar duas linhas com o mesmo numero aqui, mesmo em fazendas
        # diferentes (é exatamente o comportamento que esta migração
        # existe pra corrigir). Sobe com um animal só e confirma o efeito
        # da migração observando o schema novo direto.
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_animal(conn, 1, "100", 1)
        conn.commit()
        conn.close()

        resultado = _rodar_alembic(banco_pre_migracao, "upgrade", "c24befa94c1b")
        assert resultado.returncode == 0, resultado.stdout + resultado.stderr

        conn = sqlite3.connect(banco_pre_migracao)
        # Agora numero repetido em OUTRA fazenda é permitido...
        _inserir_animal(conn, 2, "100", 2)
        conn.commit()
        # ...mas repetir dentro da MESMA fazenda continua barrado.
        with pytest.raises(sqlite3.IntegrityError):
            _inserir_animal(conn, 3, "100", 1)
            conn.commit()
        conn.close()


class TestTravaFazendaIdNulo:
    def test_falha_com_mensagem_clara_se_existir_animal_sem_fazenda(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        _inserir_animal(conn, 1, "100", None)
        conn.commit()
        conn.close()

        resultado = _rodar_alembic(banco_pre_migracao, "upgrade", "c24befa94c1b")
        assert resultado.returncode != 0
        saida = resultado.stdout + resultado.stderr
        assert "fazenda_id NULO" in saida

        # Nada foi alterado — a migração falhou ANTES de tocar no schema, o
        # índice antigo (único GLOBAL) continua de pé e barra um segundo
        # "100", mesmo em outra fazenda.
        conn = sqlite3.connect(banco_pre_migracao)
        with pytest.raises(sqlite3.IntegrityError):
            _inserir_animal(conn, 2, "100", 2)
            conn.commit()
        conn.close()


class TestTravaDuplicataPreexistente:
    def test_falha_com_mensagem_clara_se_duplicata_ja_existir_na_mesma_fazenda(self, banco_pre_migracao):
        # Só é possível chegar nesse estado hoje via escrita direta no banco
        # (o índice antigo era único global) — a trava existe pra qualquer
        # ambiente com drift, não pro fluxo normal da aplicação.
        conn = sqlite3.connect(banco_pre_migracao)
        conn.execute("PRAGMA foreign_keys=OFF")
        _inserir_animal(conn, 1, "100", 1)
        conn.commit()
        # drop do índice único antigo pra conseguir forçar a duplicata sem
        # o sqlite barrar a própria carga do cenário de teste.
        conn.execute("DROP INDEX ix_animal_numero")
        _inserir_animal(conn, 2, "100", 1)
        conn.commit()
        conn.close()

        resultado = _rodar_alembic(banco_pre_migracao, "upgrade", "c24befa94c1b")
        assert resultado.returncode != 0
        saida = resultado.stdout + resultado.stderr
        assert "duplicado" in saida
