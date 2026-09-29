"""
Migracao e7b3a9d4c1f8 (fatia 9b) — colunas do exame preventivo (inoculacao/leitura,
resultado por animal, reagente/notificacao, reteste na lista de espera): aditiva,
idempotente por coluna (banco montado por create_all ja pode te-las), sobe e desce
limpo e a cabeca do historico e unica. Mesma tecnica de subprocesso das demais.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REV = "e7b3a9d4c1f8"
ANTERIOR = "d5a7c3e91f26"

NOVAS = {
    "cronograma_sanitario_aplicacao": {
        "fase", "inoculacao_aplicacao_id", "tipo_teste", "laudo", "leitura_prevista_em", "leitura_limite_em",
        "data_evento_antes", "hora_antes", "leitura_horas", "leitura_fora_janela", "leitura_justificativa",
    },
    "cronograma_sanitario_aplicacao_animal": {
        "exame_resultado", "espessura_mm", "reteste_em", "exame_resultado_id", "notificado_em",
        "notificado_por_usuario_id", "notificado_por_nome", "notificacao_ref",
    },
    "cronograma_sanitario_animal": {"reteste", "data_devida", "motivo_entrada"},
}


def _alembic(db_path: Path, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
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
    db = tmp_path / "exame.db"
    _alembic(db, "upgrade", ANTERIOR)
    return db


def test_sobe_adiciona_as_colunas_do_modelo(banco_anterior):
    for tabela, novas in NOVAS.items():
        assert not (novas & _colunas(banco_anterior, tabela))
    _alembic(banco_anterior, "upgrade", REV)
    for tabela, novas in NOVAS.items():
        assert novas <= _colunas(banco_anterior, tabela), tabela


def test_colunas_do_modelo_batem_com_a_migracao():
    from fazenda.models import (
        CronogramaSanitarioAnimal, CronogramaSanitarioAplicacao, CronogramaSanitarioAplicacaoAnimal,
    )
    por_tabela = {
        "cronograma_sanitario_aplicacao": CronogramaSanitarioAplicacao,
        "cronograma_sanitario_aplicacao_animal": CronogramaSanitarioAplicacaoAnimal,
        "cronograma_sanitario_animal": CronogramaSanitarioAnimal,
    }
    for tabela, novas in NOVAS.items():
        assert novas <= set(por_tabela[tabela].model_fields), tabela


def test_desce_e_sobe_de_novo_sem_erro(banco_anterior):
    _alembic(banco_anterior, "upgrade", REV)
    _alembic(banco_anterior, "downgrade", ANTERIOR)
    for tabela, novas in NOVAS.items():
        assert not (novas & _colunas(banco_anterior, tabela)), tabela
    _alembic(banco_anterior, "upgrade", "head")
    for tabela, novas in NOVAS.items():
        assert novas <= _colunas(banco_anterior, tabela), tabela


def test_idempotente_quando_uma_coluna_ja_existe(banco_anterior):
    """Banco montado por create_all ja tem colunas: a migracao nao pode falhar nem duplicar."""
    conn = sqlite3.connect(banco_anterior)
    conn.execute("ALTER TABLE cronograma_sanitario_aplicacao ADD COLUMN fase VARCHAR")
    conn.execute("ALTER TABLE cronograma_sanitario_animal ADD COLUMN reteste BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()
    _alembic(banco_anterior, "upgrade", REV)
    for tabela, novas in NOVAS.items():
        assert novas <= _colunas(banco_anterior, tabela), tabela


def test_linhas_existentes_ganham_os_padroes(banco_anterior):
    """Linha de animal da lista de espera criada ANTES da migracao ganha reteste=false e campos vazios."""
    conn = sqlite3.connect(banco_anterior)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO cronograma_sanitario_animal (cronograma_id, numero_matriz, status, data_sugestao, origem) "
            "VALUES (1, '123', 'sugerido', '2026-09-01', 'janela')"
        )
        conn.commit()
    finally:
        conn.close()
    _alembic(banco_anterior, "upgrade", REV)
    conn = sqlite3.connect(banco_anterior)
    try:
        linha = conn.execute("SELECT reteste, data_devida, motivo_entrada FROM cronograma_sanitario_animal").fetchone()
    finally:
        conn.close()
    assert linha == (0, None, None)


def test_cabeca_unica_e_esta_revisao():
    sys.path.insert(0, str(BACKEND / "scripts"))
    from check_alembic_heads import heads
    assert heads() == [REV]
