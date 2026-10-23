"""
Cadeia do sanitário v2 x alimentação (#949) — nenhum dado de tratos/sobra muda.

Banco erguido pelas próprias migrações até n5o6p7q8r9s0 (a do #949), com
dados de alimentação usando as colunas novas (tratos_pct, sobra_posicao_leitura,
trato, data_leitura, posicao_leitura) E dados sanitários mistos na mesma tabela
(preventivo antigo + BST + indução + curativo — a semente do teste da migração
A). Então: upgrade head -> alimentação idêntica; downgrade até n5o6 ->
idêntica; upgrade head de novo -> idêntica. BST, indução e curativo ficam em
todas as etapas.

SQLite sempre. Postgres com `DATABASE_URL_POSTGRES_TESTE` (job "Testes que
exigem PostgreSQL" do CI): o teste cria um banco vazio descartável e o apaga.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.test_migracao_arquivo_sanitario import (
    ANTERIOR, B, F, SANIDADES, _alembic, _esperado, _ids, _semear,
)

AGORA = datetime(2026, 10, 1, 8, 0)
D = date(2026, 9, 1)

# Tabela -> colunas comparadas (todas as do #949 + as de identidade).
ALIMENTACAO = {
    "dieta_lancamento": "id, lote, data_abertura, tratos_pct, sobra_posicao_leitura, fazenda_id",
    "consumo_alimento": "id, data, lote, alimento, quantidade, unidade, origem, trato, fazenda_id",
    "consumo_sobra": "id, data, lote, kg_sobra, data_leitura, posicao_leitura, tratos_pct, fazenda_id",
    "parametro_fazenda": "id, chave, valor, fazenda_id",
}


def _semear_alimentacao(engine) -> None:
    p = {"a": AGORA, "d": D, "d2": date(2026, 9, 2), "F": F, "B": B, "f": False}
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO dieta_lancamento (id, lote, data_abertura, criado_em, fazenda_id, tratos_pct, sobra_posicao_leitura) "
            "VALUES (:B, 1, :d, :a, :F, '40,35,25', 2), (:B + 1, 2, :d, :a, :F, NULL, NULL)"
        ), p)
        for i, trato in ((0, 1), (1, 2), (2, 3), (3, None)):
            c.execute(text(
                "INSERT INTO consumo_alimento (id, fazenda_id, data, lote, alimento, quantidade, unidade, origem, "
                "fora_da_dieta, criado_em, baixou_estoque, trato) "
                "VALUES (:i, :F, :d, 1, 'Silagem', :q, 'kg', 'manual', :f, :a, :f, :t)"
            ), {**p, "i": B + i, "q": 100.0 + i, "t": trato})
        c.execute(text(
            "INSERT INTO consumo_sobra (id, fazenda_id, data, lote, kg_sobra, criado_em, atualizado_em, "
            "data_leitura, posicao_leitura, tratos_pct) "
            "VALUES (:B, :F, :d, 1, 42.5, :a, :a, :d2, 2, '40,35,25'), (:B + 1, :F, :d, 2, 10.0, :a, :a, NULL, NULL, NULL)"
        ), p)
        c.execute(text(
            "INSERT INTO parametro_fazenda (id, chave, grupo, label, valor, tipo, atualizado_em, fazenda_id) "
            "VALUES (:B + 50, 'alimentacao_consumo_por_trato', 'alimentacao', 'l', 'true', 'bool', :a, :F)"
        ), p)


def _foto(engine) -> dict[str, list[tuple]]:
    with engine.connect() as c:
        return {
            t: [tuple(r) for r in c.execute(text(f"SELECT {cols} FROM {t} WHERE id >= :b ORDER BY id"), {"b": B})]
            for t, cols in ALIMENTACAO.items()
            if t != "parametro_fazenda"
        } | {
            "parametro_fazenda": [tuple(r) for r in c.execute(text(
                f"SELECT {ALIMENTACAO['parametro_fazenda']} FROM parametro_fazenda "
                "WHERE chave = 'alimentacao_consumo_por_trato' ORDER BY id"
            ))]
        }


def _bst_inducao_curativo_ficam(engine) -> None:
    assert _esperado(SANIDADES, True) <= _ids(engine, "sanidade")


def _cadeia(url: str) -> None:
    _alembic(url, "upgrade", ANTERIOR)
    engine = create_engine(url)
    _semear(engine)
    _semear_alimentacao(engine)
    antes = _foto(engine)
    assert antes["consumo_alimento"] and antes["consumo_sobra"] and antes["dieta_lancamento"] and antes["parametro_fazenda"]

    _alembic(url, "upgrade", "head")
    engine.dispose()
    assert _foto(engine) == antes
    _bst_inducao_curativo_ficam(engine)

    _alembic(url, "downgrade", ANTERIOR)
    engine.dispose()
    assert _foto(engine) == antes
    assert _ids(engine, "sanidade") == set(SANIDADES)  # o preventivo voltou do arquivo

    _alembic(url, "upgrade", "head")
    engine.dispose()
    assert _foto(engine) == antes
    _bst_inducao_curativo_ficam(engine)
    engine.dispose()


def test_sqlite_cadeia_completa_preserva_alimentacao(tmp_path):
    _cadeia(f"sqlite:///{tmp_path / 'compat.db'}")


URL_ADMIN = os.environ.get("DATABASE_URL_POSTGRES_TESTE", "")


@contextmanager
def banco_pg_vazio():
    """Banco Postgres novo e vazio (as migrações exigem um), apagado no fim."""
    nome = f"t_sanit_{uuid.uuid4().hex[:10]}"
    admin = create_engine(URL_ADMIN, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{nome}"'))
    try:
        yield make_url(URL_ADMIN).set(database=nome).render_as_string(hide_password=False)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)'))
        admin.dispose()


@pytest.mark.skipif(not URL_ADMIN, reason="precisa de PostgreSQL: defina DATABASE_URL_POSTGRES_TESTE")
def test_postgres_cadeia_completa_preserva_alimentacao():
    with banco_pg_vazio() as url:
        _cadeia(url)
