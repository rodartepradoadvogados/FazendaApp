"""
Plano Financeiro, fase 1.3 — migração b8c9d0e1f2a3 (preco_plano +
contrato_fazenda.preco_mensal_fechado). Roda `alembic upgrade head` de
verdade em subprocesso, em SQLite descartável (mesmo molde de
test_migracao_tabelas_faltantes.py).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parent.parent
REV = "b8c9d0e1f2a3"
REV_ANTERIOR = "f6a7b8c9d0e1"


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "FAZENDA_TESTING": "1"}
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic {' '.join(args)} falhou:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"


def test_upgrade_head_em_banco_vazio_cria_preco_plano_semeado(tmp_path):
    db = tmp_path / "vazio.db"
    _alembic(db, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db}")
    insp = sa.inspect(engine)
    assert insp.has_table("preco_plano")
    assert "preco_mensal_fechado" in {c["name"] for c in insp.get_columns("contrato_fazenda")}
    with engine.connect() as conn:
        linhas = dict(conn.execute(sa.text("SELECT plano, preco FROM preco_plano")).fetchall())
        sem_edicao = conn.execute(sa.text("SELECT COUNT(*) FROM preco_plano WHERE atualizado_em IS NOT NULL")).scalar()
    engine.dispose()
    assert linhas == {"standard": 250.0, "silver": 350.0, "gold": 420.0, "diamond": 500.0, "financeiro": 200.0}
    assert sem_edicao == 0
    # Os preços semeados batem com o padrão do código (não deixa divergir).
    from fazenda.models.planos import PLANOS_CATALOGO

    assert {k: v["preco"] for k, v in PLANOS_CATALOGO.items()} == linhas


def test_backfill_congela_so_contratos_ativos_com_plano_e_nao_muda_valor(tmp_path):
    """Banco já na revisão anterior, com contratos de 4 tipos; depois do
    upgrade só o ATIVO com plano de catálogo ganha preço fechado (o de
    catálogo de hoje); nada que já era cobrado muda."""
    db = tmp_path / "backfill.db"
    _alembic(db, "upgrade", REV_ANTERIOR)
    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        for fid in (11, 12, 13, 14):
            conn.execute(sa.text("INSERT INTO fazenda (id, nome, ativa, criado_em) VALUES (:i, :n, 1, '2026-10-01 00:00:00')"),
                {"i": fid, "n": f"F{fid}"},
            )
        agora = "2026-10-01 00:00:00"
        for fid, plano, status in ((11, "gold", "ativo"), (12, "standard", "aguardando_aprovacao"), (13, None, "ativo"), (14, "silver", "suspenso")):
            conn.execute(
                sa.text(
                    "INSERT INTO contrato_fazenda (fazenda_id, plano, status, ciclo_pagamento, criado_em, atualizado_em) "
                    "VALUES (:f, :p, :s, 'mensal', :a, :a)"
                ),
                {"f": fid, "p": plano, "s": status, "a": agora},
            )
    engine.dispose()

    _alembic(db, "upgrade", "head")
    # Idempotente: rodar de novo não quebra nem muda nada.
    _alembic(db, "downgrade", REV_ANTERIOR)
    _alembic(db, "upgrade", "head")

    engine = sa.create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        fechado = dict(conn.execute(sa.text("SELECT fazenda_id, preco_mensal_fechado FROM contrato_fazenda")).fetchall())
    engine.dispose()
    # (a fazenda #1 grandfathered, criada por migração antiga, é sob medida: segue None)
    fechado.pop(1, None)
    assert fechado == {11: 420.0, 12: None, 13: None, 14: None}
