"""
Migração 089c4e98da6d (fazenda.eh_teste) — marca `eh_teste=True` só na
fazenda cujo nome é EXATAMENTE "Fazenda Teste", nunca por id (ver docstring
da migração). Mesma técnica de subprocesso das demais migrações desta
"fundação".
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


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
    db_path = tmp_path / "eh_teste.db"
    _rodar_alembic(db_path, "upgrade", "c24befa94c1b")
    return db_path


class TestMarcaSoPeloNomeExato:
    def test_marca_fazenda_teste_de_nome_exato(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        conn.execute(
            "INSERT INTO fazenda (id, nome, ativa, criado_em, eh_empresa_cowdata) "
            "VALUES (900, 'Fazenda Teste', 1, CURRENT_TIMESTAMP, 0)"
        )
        conn.commit()
        conn.close()

        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        eh_teste_900 = conn.execute("SELECT eh_teste FROM fazenda WHERE id = 900").fetchone()[0]
        eh_teste_1 = conn.execute("SELECT eh_teste FROM fazenda WHERE id = 1").fetchone()[0]
        conn.close()
        assert eh_teste_900 == 1
        assert eh_teste_1 == 0, "a fazenda real (#1, semeada pelo piloto) nunca deveria ser marcada"

    def test_nome_parecido_mas_nao_exato_nao_e_marcado(self, banco_pre_migracao):
        conn = sqlite3.connect(banco_pre_migracao)
        conn.execute(
            "INSERT INTO fazenda (id, nome, ativa, criado_em, eh_empresa_cowdata) "
            "VALUES (900, 'Fazenda Teste 2', 1, CURRENT_TIMESTAMP, 0)"
        )
        conn.commit()
        conn.close()

        saida = _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        conn = sqlite3.connect(banco_pre_migracao)
        eh_teste_900 = conn.execute("SELECT eh_teste FROM fazenda WHERE id = 900").fetchone()[0]
        conn.close()
        assert eh_teste_900 == 0
        assert "nenhuma fazenda com nome exato" in saida

    def test_coluna_nasce_com_default_false_pra_quem_ja_existia(self, banco_pre_migracao):
        # A fazenda #1 ("Jairo Nasser") já existia antes desta migração —
        # confirma que o ADD COLUMN não a deixou com eh_teste nulo.
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        conn = sqlite3.connect(banco_pre_migracao)
        eh_teste_1 = conn.execute("SELECT eh_teste FROM fazenda WHERE id = 1").fetchone()[0]
        conn.close()
        assert eh_teste_1 == 0
