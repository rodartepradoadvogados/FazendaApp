"""
Migração e3bc1c978262 (Fase P1 do refactor Alimento/Estoque) — ver
backend/alembic/versions/e3bc1c978262_alimento_estoque_p1_gaps.py.

Três backfills/colunas aditivas, cobertos aqui via `alembic upgrade`/
`downgrade` de verdade (mesmo padrão de
test_migracao_backfill_tipos_administrador_contador.py — subprocesso com
DATABASE_URL própria, porque alembic/env.py lê a env var no import de
fazenda.database):

1. `AnaliseBromatologica.alimento_id` — backfill por igualdade exata de nome
   com `Alimento.nome`, escopado por fazenda_id (incluindo NULL).
2. `Estoque.categoria_alimento_id` — coluna nova, backfill de UMA VEZ a
   partir de `Alimento.categoria_alimento_id` quando o item já está
   vinculado a um Alimento com categoria.
3. `Alimento.estoque_preferido_id` — coluna nova, sem nenhum backfill (fica
   NULL para todo Alimento já existente).
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


def _seed_pre_p1(conn: sqlite3.Connection) -> dict:
    """Semeia dados como se a fazenda já existisse ANTES da Fase P1: um
    Alimento com categoria, um item de Estoque vinculado a ele (sem
    categoria própria ainda) e laudos bromatológicos — um casando por nome,
    outro não. Cobre fazenda_id=1, fazenda_id=2 (isolamento) e fazenda_id
    NULL (piloto legado)."""
    agora = datetime.datetime.utcnow().isoformat()
    ids = {}

    for fid in (1, 2, None):
        conn.execute(
            "INSERT INTO categoria_alimento (nome, ativo, criado_em, fazenda_id) VALUES (?,1,?,?)",
            ("Volumoso", agora, fid),
        )
        cat_id = conn.execute(
            "SELECT id FROM categoria_alimento WHERE fazenda_id IS ? AND nome='Volumoso'", (fid,)
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO alimento (nome, categoria_alimento_id, ativo, criado_em, atualizado_em, fazenda_id) "
            "VALUES ('Silagem de milho', ?, 1, ?, ?, ?)",
            (cat_id, agora, agora, fid),
        )
        alimento_id = conn.execute(
            "SELECT id FROM alimento WHERE fazenda_id IS ? AND nome='Silagem de milho'", (fid,)
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO estoque (nome, alimento_id, atualizado_em, fazenda_id) VALUES (?,?,?,?)",
            (f"Silagem Lote A (fazenda {fid})", alimento_id, agora, fid),
        )
        estoque_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Laudo que casa por nome exato.
        conn.execute(
            "INSERT INTO analise_bromatologica (data, alimento, criado_em, fazenda_id) VALUES ('2026-01-01', 'Silagem de milho', ?, ?)",
            (agora, fid),
        )
        laudo_casa_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Laudo que NÃO casa com nenhum Alimento desta fazenda.
        conn.execute(
            "INSERT INTO analise_bromatologica (data, alimento, criado_em, fazenda_id) VALUES ('2026-02-01', 'Ingrediente fantasma', ?, ?)",
            (agora, fid),
        )
        laudo_orfao_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        ids[fid] = {
            "categoria_id": cat_id, "alimento_id": alimento_id, "estoque_id": estoque_id,
            "laudo_casa_id": laudo_casa_id, "laudo_orfao_id": laudo_orfao_id,
        }
    return ids


def test_backfill_alimento_id_do_laudo_por_nome_exato_escopado_por_fazenda(tmp_path):
    db_path = tmp_path / "p1_laudo.db"
    _rodar_alembic(db_path, "upgrade", "bd9c8a966d75")

    conn = sqlite3.connect(db_path)
    ids = _seed_pre_p1(conn)
    # Fazenda 2 já tinha "Contador" adicionado manualmente — não relevante
    # aqui, mas garante que o backfill de tipo_pessoa (migração anterior)
    # não interfere. Fecha a conexão antes do subprocesso do alembic.
    conn.commit()
    conn.close()

    _rodar_alembic(db_path, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    for fid in (1, 2, None):
        info = ids[fid]
        alimento_id_laudo, = conn.execute(
            "SELECT alimento_id FROM analise_bromatologica WHERE id=?", (info["laudo_casa_id"],)
        ).fetchone()
        assert alimento_id_laudo == info["alimento_id"], f"fazenda {fid}: laudo que casa por nome não foi ligado"

        alimento_id_orfao, = conn.execute(
            "SELECT alimento_id FROM analise_bromatologica WHERE id=?", (info["laudo_orfao_id"],)
        ).fetchone()
        assert alimento_id_orfao is None, f"fazenda {fid}: laudo sem Alimento correspondente ficou com id inventado"
    conn.close()


def test_backfill_categoria_alimento_id_do_estoque_copia_da_categoria_do_alimento(tmp_path):
    db_path = tmp_path / "p1_categoria.db"
    _rodar_alembic(db_path, "upgrade", "bd9c8a966d75")

    conn = sqlite3.connect(db_path)
    ids = _seed_pre_p1(conn)
    conn.commit()
    conn.close()

    _rodar_alembic(db_path, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    for fid in (1, 2, None):
        info = ids[fid]
        categoria_estoque, = conn.execute(
            "SELECT categoria_alimento_id FROM estoque WHERE id=?", (info["estoque_id"],)
        ).fetchone()
        assert categoria_estoque == info["categoria_id"], f"fazenda {fid}: categoria não foi copiada do Alimento"
    conn.close()


def test_estoque_preferido_id_fica_null_sem_backfill(tmp_path):
    db_path = tmp_path / "p1_preferido.db"
    _rodar_alembic(db_path, "upgrade", "bd9c8a966d75")

    conn = sqlite3.connect(db_path)
    _seed_pre_p1(conn)
    conn.commit()
    conn.close()

    _rodar_alembic(db_path, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    valores = conn.execute("SELECT estoque_preferido_id FROM alimento").fetchall()
    conn.close()
    assert valores  # a fixture semeou pelo menos um Alimento por fazenda
    assert all(v == (None,) for v in valores)


def test_backfill_e_idempotente(tmp_path):
    db_path = tmp_path / "p1_idempotente.db"
    _rodar_alembic(db_path, "upgrade", "bd9c8a966d75")

    conn = sqlite3.connect(db_path)
    ids = _seed_pre_p1(conn)
    conn.commit()
    conn.close()

    _rodar_alembic(db_path, "upgrade", "head")
    _rodar_alembic(db_path, "upgrade", "head")  # roda de novo — não pode duplicar nem quebrar

    conn = sqlite3.connect(db_path)
    for fid in (1, 2, None):
        info = ids[fid]
        alimento_id_laudo, = conn.execute(
            "SELECT alimento_id FROM analise_bromatologica WHERE id=?", (info["laudo_casa_id"],)
        ).fetchone()
        assert alimento_id_laudo == info["alimento_id"]
        categoria_estoque, = conn.execute(
            "SELECT categoria_alimento_id FROM estoque WHERE id=?", (info["estoque_id"],)
        ).fetchone()
        assert categoria_estoque == info["categoria_id"]
    conn.close()


def test_downgrade_e_reupgrade_reproduz_o_mesmo_estado(tmp_path):
    """Round-trip completo: upgrade -> downgrade até antes de e3bc1c978262 ->
    upgrade head chega exatamente no mesmo estado (upgrade é determinístico)
    — mesma garantia de idempotência exigida pela migração de tipo_pessoa.

    O downgrade aponta pro down_revision de e3bc1c978262 (`bd9c8a966d75`) em
    vez de "-1": "-1" desfaz só o ÚLTIMO passo a partir de head, que deixou
    de ser e3bc1c978262 assim que alguma migração nova foi encadeada depois
    dela (ver dieta_item_programado.base_quantidade) — o teste precisa
    continuar mirando ESTA migração específica, não "o que for head agora"."""
    db_path = tmp_path / "p1_roundtrip.db"
    _rodar_alembic(db_path, "upgrade", "bd9c8a966d75")

    conn = sqlite3.connect(db_path)
    ids = _seed_pre_p1(conn)
    conn.commit()
    conn.close()

    _rodar_alembic(db_path, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    estado_antes = {
        "analise": conn.execute("SELECT id, alimento_id FROM analise_bromatologica ORDER BY id").fetchall(),
        "estoque": conn.execute("SELECT id, categoria_alimento_id FROM estoque ORDER BY id").fetchall(),
    }
    conn.close()

    _rodar_alembic(db_path, "downgrade", "bd9c8a966d75")

    conn = sqlite3.connect(db_path)
    # As colunas novas somem no downgrade — confirma que a coluna foi
    # realmente derrubada (não só zerada).
    colunas_estoque = {r[1] for r in conn.execute("PRAGMA table_info(estoque)")}
    colunas_alimento = {r[1] for r in conn.execute("PRAGMA table_info(alimento)")}
    assert "categoria_alimento_id" not in colunas_estoque
    assert "estoque_preferido_id" not in colunas_alimento
    # E o laudo que tinha sido ligado por id volta a NULL.
    for fid in (1, 2, None):
        info = ids[fid]
        alimento_id_laudo, = conn.execute(
            "SELECT alimento_id FROM analise_bromatologica WHERE id=?", (info["laudo_casa_id"],)
        ).fetchone()
        assert alimento_id_laudo is None
    conn.close()

    _rodar_alembic(db_path, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    estado_depois = {
        "analise": conn.execute("SELECT id, alimento_id FROM analise_bromatologica ORDER BY id").fetchall(),
        "estoque": conn.execute("SELECT id, categoria_alimento_id FROM estoque ORDER BY id").fetchall(),
    }
    conn.close()

    assert estado_antes == estado_depois
