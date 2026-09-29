"""
Migracao d5a7c3e91f26 (fatia 9) — tabela `cronograma_sanitario_vinculo`:
aditiva, idempotente (banco montado por create_all ja pode te-la), sobe e desce
limpo, cabeca unica. Mesma tecnica de subprocesso das demais migracoes.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REV = "d5a7c3e91f26"
ANTERIOR = "c4e8a1f7b352"
TABELA = "cronograma_sanitario_vinculo"


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
    db = tmp_path / "vinculo.db"
    _alembic(db, "upgrade", ANTERIOR)
    return db


def test_sobe_cria_a_tabela_com_as_colunas_do_modelo(banco_anterior):
    assert not _tem_tabela(banco_anterior)
    _alembic(banco_anterior, "upgrade", REV)
    assert {"id", "fazenda_id", "cronograma_id", "tipo", "alvo_id", "numero_lancamento", "estado", "valor", "modo",
            "subtipo", "rotulo", "descricao", "vencimento", "criado_por_usuario_id", "criado_em",
            "encerrado_por_usuario_id", "encerrado_em", "motivo_encerramento"} <= _colunas(banco_anterior)


def test_desce_e_sobe_de_novo_sem_erro(banco_anterior):
    _alembic(banco_anterior, "upgrade", REV)
    _alembic(banco_anterior, "downgrade", ANTERIOR)
    assert not _tem_tabela(banco_anterior)
    _alembic(banco_anterior, "upgrade", "head")
    assert _tem_tabela(banco_anterior)


def test_idempotente_quando_a_tabela_ja_existe(banco_anterior):
    """Banco montado por create_all ja tem a tabela: a migracao nao pode falhar nem duplicar."""
    conn = sqlite3.connect(banco_anterior)
    conn.execute(f"CREATE TABLE {TABELA} (id INTEGER PRIMARY KEY, cronograma_id INTEGER, tipo TEXT, alvo_id INTEGER)")
    conn.commit()
    conn.close()
    _alembic(banco_anterior, "upgrade", REV)
    assert _tem_tabela(banco_anterior)
    _alembic(banco_anterior, "downgrade", ANTERIOR)
    assert not _tem_tabela(banco_anterior)


def test_head_e_esta_revisao():
    sys.path.insert(0, str(BACKEND / "scripts"))
    from check_alembic_heads import heads
    assert heads() == [REV]
