"""
Migração d4a8e1b7c935 — `estoque.produto_leite` (marcador "Produto de leite (venda ao laticínio)").

O que se trava (mesma técnica de subprocesso das demais migrações; ver
test_migracao_vale_alimentacao_natureza.py):

 - a coluna passa a existir, NULLABLE e sem `server_default` (a migração roda no boot da
   API; nada de reescrever a tabela `estoque`);
 - ADITIVA e sem backfill: nenhum item existente é marcado, desativado ou excluído;
 - rodar o upgrade com a coluna já criada (o `create_all` do boot) NÃO aborta;
 - o downgrade remove a coluna e o resto de `estoque` sobrevive.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REVISAO_ANTERIOR = "c6f2a9d4e817"
REVISAO = "d4a8e1b7c935"


def _rodar_alembic(db_path: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    return r.stdout


def _colunas(db_path: Path) -> dict[str, dict]:
    conn = sqlite3.connect(db_path)
    info = {c[1]: {"notnull": c[3], "default": c[4]} for c in conn.execute("PRAGMA table_info(estoque)")}
    conn.close()
    return info


@pytest.fixture
def banco_pre_migracao(tmp_path):
    db_path = tmp_path / "estoque_produto_leite.db"
    _rodar_alembic(db_path, "upgrade", REVISAO_ANTERIOR)
    return db_path


def test_coluna_nova_nullable_sem_default_e_nenhum_item_marcado(banco_pre_migracao):
    assert "produto_leite" not in _colunas(banco_pre_migracao)
    conn = sqlite3.connect(banco_pre_migracao)
    conn.execute("INSERT INTO estoque (nome, atualizado_em) VALUES ('Leite', '2026-10-09 10:00:00')")
    conn.execute("INSERT INTO estoque (nome, atualizado_em) VALUES ('Leite Cru Refrigerado', '2026-10-09 10:00:00')")
    conn.commit()
    conn.close()

    _rodar_alembic(banco_pre_migracao, "upgrade", REVISAO)

    col = _colunas(banco_pre_migracao)["produto_leite"]
    assert col["notnull"] == 0 and col["default"] is None
    conn = sqlite3.connect(banco_pre_migracao)
    linhas = conn.execute("SELECT nome, produto_leite, ativo FROM estoque ORDER BY id").fetchall()
    conn.close()
    # Sem backfill: ninguém marcado (NULL lê como falso), ninguém desativado, ninguém removido.
    assert linhas == [("Leite", None, None), ("Leite Cru Refrigerado", None, None)]


def test_upgrade_nao_aborta_com_a_coluna_ja_criada(banco_pre_migracao):
    conn = sqlite3.connect(banco_pre_migracao)
    conn.execute("ALTER TABLE estoque ADD COLUMN produto_leite BOOLEAN")
    conn.commit()
    conn.close()
    _rodar_alembic(banco_pre_migracao, "upgrade", REVISAO)
    assert "produto_leite" in _colunas(banco_pre_migracao)
    assert REVISAO in _rodar_alembic(banco_pre_migracao, "history", "-r", "base:current")


def test_downgrade_remove_a_coluna_e_o_resto_do_item_sobrevive(banco_pre_migracao):
    _rodar_alembic(banco_pre_migracao, "upgrade", REVISAO)
    conn = sqlite3.connect(banco_pre_migracao)
    conn.execute("INSERT INTO estoque (nome, unidade, produto_leite, atualizado_em) VALUES ('Leite Cru Refrigerado', 'L', 1, '2026-10-09 10:00:00')")
    conn.commit()
    conn.close()

    _rodar_alembic(banco_pre_migracao, "downgrade", REVISAO_ANTERIOR)

    assert "produto_leite" not in _colunas(banco_pre_migracao)
    conn = sqlite3.connect(banco_pre_migracao)
    assert conn.execute("SELECT nome, unidade FROM estoque").fetchall() == [("Leite Cru Refrigerado", "L")]
    conn.close()
    # E sobe de novo, com a coluna vazia.
    _rodar_alembic(banco_pre_migracao, "upgrade", REVISAO)
    conn = sqlite3.connect(banco_pre_migracao)
    assert conn.execute("SELECT produto_leite FROM estoque").fetchall() == [(None,)]
    conn.close()
