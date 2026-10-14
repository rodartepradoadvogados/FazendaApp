"""
Migracao f6a7b8c9d0e1: adiciona `documento_arquivado.conteudo` e torna
`caminho_storage` anulavel. Regressao: `op.alter_column` direto gera
`ALTER COLUMN ... DROP NOT NULL`, que o SQLite rejeita e derruba o boot de todo
`TestClient(main.app)` (o lifespan roda `_aplicar_alembic`). Usa
`batch_alter_table`. Roda so em SQLite local (subprocesso), nunca em producao.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REV = "f6a7b8c9d0e1"
ANTERIOR = "g7h8i9j0k1l2"


def _alembic(db_path: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env.update({"DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"})
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"


def _info(db_path: Path) -> dict[str, tuple[int, int]]:
    """nome -> (notnull, ...)."""
    conn = sqlite3.connect(db_path)
    try:
        return {r[1]: (r[3],) for r in conn.execute("PRAGMA table_info(documento_arquivado)")}
    finally:
        conn.close()


@pytest.fixture
def banco_anterior(tmp_path):
    db = tmp_path / "docarq.db"
    _alembic(db, "upgrade", ANTERIOR)
    return db


def test_sobe_e_desce_em_sqlite(banco_anterior):
    antes = _info(banco_anterior)
    if not antes:
        pytest.skip("documento_arquivado ainda nao existe na revisao anterior (migracao e no-op)")
    assert "conteudo" not in antes
    _alembic(banco_anterior, "upgrade", REV)
    depois = _info(banco_anterior)
    assert "conteudo" in depois
    assert depois["caminho_storage"] == (0,)  # anulavel
    _alembic(banco_anterior, "downgrade", ANTERIOR)
    volta = _info(banco_anterior)
    assert "conteudo" not in volta
    assert volta["caminho_storage"] == (1,)  # NOT NULL de novo
