"""
Migração bd9c8a966d75 (backfill de TipoPessoa "Administrador"/"Contador" em
toda fazenda já existente) — ver PR claude/backfill-tipos-administrador-contador.

Contexto: a PR #602 adicionou "Administrador"/"Contador" a TIPOS_PESSOA e um
filtro de "papel funcional" em usePessoasAtivas (exige um desses 5 tipos para
aparecer em qualquer lista de Responsável). Mas seed_tipos_pessoa só semeia
os tipos padrão UMA VEZ por fazenda (SeedFlag) — toda fazenda que já existia
antes da PR #602 NUNCA ganha os dois tipos novos sozinha. Sem este backfill,
"Administrador"/"Contador" nunca aparecem como opção numa fazenda antiga, e
qualquer pessoa cujo único papel era administrativo (ex.: o dono da fazenda,
cadastrado como "Geral") some silenciosamente de toda lista de Responsável.

Roda o `alembic upgrade` de verdade, em processo separado (mesmo padrão de
test_migracao_fazenda_id_backfill.py — alembic/env.py lê DATABASE_URL fixado
no import de fazenda.database, então só um subprocesso com env var própria
isola o teste).
"""
from __future__ import annotations

import datetime
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

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


def test_backfill_adiciona_administrador_e_contador_sem_duplicar(tmp_path):
    db_path = tmp_path / "backfill_tipos.db"
    # Sobe até IMEDIATAMENTE ANTES do backfill — simula uma fazenda antiga,
    # já com tipo_pessoa populado do jeito que seed_tipos_pessoa deixava
    # ANTES de Administrador/Contador existirem em TIPOS_PESSOA.
    _rodar_alembic(db_path, "upgrade", "0bfa9fbc2926")

    conn = sqlite3.connect(db_path)
    agora = datetime.datetime.utcnow().isoformat()
    # Fazenda 1: sem Administrador nem Contador (caso comum pré-#602) — tem
    # "Geral", igual ao dono/responsável que a PR #602 tirou das listas.
    conn.execute("INSERT INTO tipo_pessoa (nome, ativo, criado_em, fazenda_id) VALUES (?,1,?,1)", ("Funcionário", agora))
    conn.execute("INSERT INTO tipo_pessoa (nome, ativo, criado_em, fazenda_id) VALUES (?,1,?,1)", ("Geral", agora))
    # Fazenda 2: já tinha "Contador" adicionado manualmente pelo usuário
    # (botão "+") antes deste backfill — não pode duplicar.
    conn.execute("INSERT INTO tipo_pessoa (nome, ativo, criado_em, fazenda_id) VALUES (?,1,?,2)", ("Contador", agora))
    # Piloto legado (fazenda_id NULL) também precisa ser coberto.
    conn.execute("INSERT INTO tipo_pessoa (nome, ativo, criado_em, fazenda_id) VALUES (?,1,?,NULL)", ("Diarista", agora))
    conn.commit()
    conn.close()

    _rodar_alembic(db_path, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    linhas = conn.execute("SELECT fazenda_id, nome FROM tipo_pessoa ORDER BY fazenda_id IS NULL DESC, fazenda_id, nome").fetchall()
    conn.close()

    assert (1, "Administrador") in linhas
    assert (1, "Contador") in linhas
    assert (2, "Administrador") in linhas
    assert linhas.count((2, "Contador")) == 1  # não duplicou o que já existia
    assert (None, "Administrador") in linhas
    assert (None, "Contador") in linhas


def test_backfill_e_idempotente(tmp_path):
    db_path = tmp_path / "backfill_tipos_idempotente.db"
    _rodar_alembic(db_path, "upgrade", "0bfa9fbc2926")
    conn = sqlite3.connect(db_path)
    agora = datetime.datetime.utcnow().isoformat()
    conn.execute("INSERT INTO tipo_pessoa (nome, ativo, criado_em, fazenda_id) VALUES (?,1,?,1)", ("Funcionário", agora))
    conn.commit()
    conn.close()

    _rodar_alembic(db_path, "upgrade", "head")
    _rodar_alembic(db_path, "downgrade", "-1")
    _rodar_alembic(db_path, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    contagem = conn.execute(
        "SELECT nome, COUNT(*) FROM tipo_pessoa WHERE nome IN ('Administrador','Contador') GROUP BY nome"
    ).fetchall()
    conn.close()
    assert dict(contagem) == {"Administrador": 1, "Contador": 1}
