"""
Migracao a3c9e5b71d24 (rotina da lista de espera): ADITIVA — coluna opcional
`calendario_sanitario.dias_antecedencia_lista_espera` e tabela
`rotina_lista_espera_estado` (uma linha por fazenda). Sobe/desce limpo, e
idempotente (banco montado por create_all ja pode ter tudo). Roda so em SQLite
local (subprocesso com DATABASE_URL proprio), nunca em producao.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REV = "a3c9e5b71d24"
ANTERIOR = "f1b6d2a8c904"
COLUNAS_ESTADO = {
    "id", "fazenda_id", "ultima_execucao_em", "ultima_execucao_origem", "ultima_execucao_status",
    "ultima_execucao_entraram", "ultima_execucao_regras", "ultima_execucao_regras_na_janela", "ultimo_erro",
    "ultima_diaria_em", "ultimo_aviso_em", "em_execucao_ate",
}


def _alembic(db_path: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env.update({"DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"})
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    return r.stdout + r.stderr


def _colunas(db_path: Path, tabela: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})")}
    finally:
        conn.close()


@pytest.fixture
def banco_anterior(tmp_path):
    db = tmp_path / "rotina.db"
    _alembic(db, "upgrade", ANTERIOR)
    return db


def test_sobe_adiciona_coluna_e_tabela(banco_anterior):
    assert "dias_antecedencia_lista_espera" not in _colunas(banco_anterior, "calendario_sanitario")
    assert not _colunas(banco_anterior, "rotina_lista_espera_estado")
    _alembic(banco_anterior, "upgrade", REV)
    assert "dias_antecedencia_lista_espera" in _colunas(banco_anterior, "calendario_sanitario")
    assert _colunas(banco_anterior, "rotina_lista_espera_estado") == COLUNAS_ESTADO


def test_modelo_bate_com_a_migracao():
    from fazenda.models import CalendarioSanitario, RotinaListaEsperaEstado
    assert "dias_antecedencia_lista_espera" in CalendarioSanitario.model_fields
    assert set(RotinaListaEsperaEstado.model_fields) == COLUNAS_ESTADO


def test_desce_e_sobe_de_novo(banco_anterior):
    _alembic(banco_anterior, "upgrade", REV)
    _alembic(banco_anterior, "downgrade", ANTERIOR)
    assert "dias_antecedencia_lista_espera" not in _colunas(banco_anterior, "calendario_sanitario")
    assert not _colunas(banco_anterior, "rotina_lista_espera_estado")
    _alembic(banco_anterior, "upgrade", REV)
    assert _colunas(banco_anterior, "rotina_lista_espera_estado") == COLUNAS_ESTADO


def test_regra_existente_fica_com_antecedencia_nula(banco_anterior):
    _alembic(banco_anterior, "upgrade", REV)
    # migracao aditiva: nada de backfill, coluna aceita NULL
    conn = sqlite3.connect(banco_anterior)
    try:
        info = {r[1]: r for r in conn.execute("PRAGMA table_info(calendario_sanitario)")}
        assert info["dias_antecedencia_lista_espera"][3] == 0  # notnull = 0
    finally:
        conn.close()


def test_upgrade_idempotente_com_tabela_ja_criada(banco_anterior):
    conn = sqlite3.connect(banco_anterior)
    conn.execute("ALTER TABLE calendario_sanitario ADD COLUMN dias_antecedencia_lista_espera INTEGER")
    conn.execute("CREATE TABLE rotina_lista_espera_estado (id INTEGER PRIMARY KEY, fazenda_id INTEGER)")
    conn.commit()
    conn.close()
    _alembic(banco_anterior, "upgrade", REV)


def test_uma_cabeca_so():
    sys.path.insert(0, str(BACKEND / "scripts"))
    from check_alembic_heads import heads
    assert heads() == [REV]
