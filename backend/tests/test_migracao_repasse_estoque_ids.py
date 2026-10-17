"""
Migração m4n5o6p7q8r9 — coluna `repasse_config.estoque_ids_json` (vários produtos vinculados ao adesivo): aditiva,
com cópia do produto único que já existia, idempotente, sobe e desce limpo, cabeça única. SQLite temporário.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REV = "m4n5o6p7q8r9"
ANTERIOR = "l3m4n5o6p7q8"


def _alembic(db_path: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    return r.stdout + r.stderr


def _colunas(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(repasse_config)")}
    finally:
        conn.close()


@pytest.fixture
def banco_anterior(tmp_path):
    db = tmp_path / "repasse_ids.db"
    _alembic(db, "upgrade", ANTERIOR)
    return db


def test_sobe_com_a_coluna_nova(banco_anterior):
    assert "estoque_ids_json" not in _colunas(banco_anterior)
    _alembic(banco_anterior, "upgrade", REV)
    assert "estoque_ids_json" in _colunas(banco_anterior)


def test_quem_ja_tinha_um_produto_passa_a_ter_a_lista_com_ele(banco_anterior):
    conn = sqlite3.connect(banco_anterior)
    conn.execute("INSERT INTO repasse_config (fazenda_id, usar, estoque_id, dias_apos_servico, repetir, repetir_cada_dias, repeticoes, mostrar_na_agenda, quem_entra, atualizado_em) "
                 "VALUES (NULL, 1, 7, 14, 0, 21, 1, 1, 'todas', CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO repasse_config (fazenda_id, usar, estoque_id, dias_apos_servico, repetir, repetir_cada_dias, repeticoes, mostrar_na_agenda, quem_entra, atualizado_em) "
                 "VALUES (1, 1, NULL, 14, 0, 21, 1, 1, 'todas', CURRENT_TIMESTAMP)")
    conn.commit()
    conn.close()
    _alembic(banco_anterior, "upgrade", REV)
    conn = sqlite3.connect(banco_anterior)
    try:
        linhas = dict(conn.execute("SELECT COALESCE(fazenda_id, 0), estoque_ids_json FROM repasse_config").fetchall())
    finally:
        conn.close()
    assert linhas[0] == "[7]" and linhas[1] is None


def test_desce_e_sobe_de_novo_sem_erro(banco_anterior):
    _alembic(banco_anterior, "upgrade", REV)
    _alembic(banco_anterior, "downgrade", ANTERIOR)
    assert "estoque_ids_json" not in _colunas(banco_anterior)
    _alembic(banco_anterior, "upgrade", "head")
    assert "estoque_ids_json" in _colunas(banco_anterior)


def test_idempotente_quando_a_coluna_ja_existe(banco_anterior):
    conn = sqlite3.connect(banco_anterior)
    conn.execute("ALTER TABLE repasse_config ADD COLUMN estoque_ids_json VARCHAR")
    conn.commit()
    conn.close()
    _alembic(banco_anterior, "upgrade", REV)
    assert "estoque_ids_json" in _colunas(banco_anterior)


def test_cabeca_unica():
    sys.path.insert(0, str(BACKEND / "scripts"))
    from check_alembic_heads import heads
    assert len(heads()) == 1
