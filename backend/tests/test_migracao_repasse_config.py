"""
Migracao f1b6d2a8c904 (fatia 10) — tabela `repasse_config` (deteccao de cio de
repasse por fazenda): aditiva, idempotente, sobe e desce limpo, cabeca unica.
Sempre em SQLite temporario (subprocesso com DATABASE_URL proprio).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REV = "f1b6d2a8c904"
ANTERIOR = "e7b3a9d4c1f8"
TABELA = "repasse_config"


def _alembic(db_path: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    return r.stdout + r.stderr


def _colunas(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({TABELA})")}
    finally:
        conn.close()


def _tem_tabela(db_path: Path) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABELA,)).fetchone() is not None
    finally:
        conn.close()


@pytest.fixture
def banco_anterior(tmp_path):
    db = tmp_path / "repasse.db"
    _alembic(db, "upgrade", ANTERIOR)
    return db


def test_sobe_cria_a_tabela_com_as_colunas_do_modelo(banco_anterior):
    assert not _tem_tabela(banco_anterior)
    _alembic(banco_anterior, "upgrade", REV)
    assert {"id", "fazenda_id", "usar", "estoque_id", "dias_apos_servico", "repetir", "repetir_cada_dias",
            "repeticoes", "mostrar_na_agenda", "quem_entra", "atualizado_em",
            "atualizado_por_usuario_id"} <= _colunas(banco_anterior)


def test_desce_e_sobe_de_novo_sem_erro(banco_anterior):
    _alembic(banco_anterior, "upgrade", REV)
    _alembic(banco_anterior, "downgrade", ANTERIOR)
    assert not _tem_tabela(banco_anterior)
    _alembic(banco_anterior, "upgrade", "head")
    assert _tem_tabela(banco_anterior)


def test_idempotente_quando_a_tabela_ja_existe(banco_anterior):
    conn = sqlite3.connect(banco_anterior)
    conn.execute(f"CREATE TABLE {TABELA} (id INTEGER PRIMARY KEY, fazenda_id INTEGER)")
    conn.commit()
    conn.close()
    _alembic(banco_anterior, "upgrade", REV)
    assert _tem_tabela(banco_anterior)
    _alembic(banco_anterior, "downgrade", ANTERIOR)
    assert not _tem_tabela(banco_anterior)


def test_cabeca_unica_e_revisao_no_historico():
    sys.path.insert(0, str(BACKEND / "scripts"))
    from check_alembic_heads import heads
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    assert len(heads()) == 1
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    assert REV in {r.revision for r in ScriptDirectory.from_config(cfg).walk_revisions()}
