"""
Migração f3c5e07b91aa — média das verbas variáveis habituais no 13º, nas
férias e na rescisão.

O que estes testes travam, e por que cada um já custou um deploy em algum
projeto:

1. **Idempotência.** `database.py` chama `SQLModel.metadata.create_all` na
   subida da aplicação, então em deploy as colunas novas podem JÁ EXISTIR
   quando o `upgrade head` roda. Um `add_column` cru abortaria o upgrade
   INTEIRO e a API não subiria — a migração roda no BOOT. O teste simula
   exatamente esse cenário: cria as colunas à mão, carimba a revisão anterior
   e manda subir.
2. **Nenhum backfill, nenhum dado tocado.** Férias, 13º e rescisões que já
   existiam continuam com os MESMOS valores e com a média em NULL. Recalcular
   a média de um lançamento já pago reescreveria em cima de dinheiro que já
   saiu — e NULL é a informação certa: "esta média não foi apurada", que é
   diferente de "foi apurada e deu zero".
3. **Cabeça única.** Duas cabeças quebram a CI e o boot.

Mesma técnica de subprocesso das demais migrações (ver
test_migracao_vale_alimentacao_natureza.py e
test_migracao_folha_discriminacao_congelada.py).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REVISAO = "f3c5e07b91aa"
REVISAO_ANTERIOR = "d4a17c60be92"

COLUNAS_NOVAS = {
    "ferias_funcionario": ["media_variaveis", "media_variaveis_composicao"],
    "decimo_terceiro": ["media_variaveis", "media_variaveis_composicao"],
    "rescisao_funcionario": [
        "media_variaveis_decimo_terceiro", "media_variaveis_ferias",
        "media_variaveis_aviso_previo", "media_variaveis_composicao",
    ],
}


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


def _colunas(db_path: Path, tabela: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {linha[1] for linha in conn.execute(f"PRAGMA table_info({tabela})")}
    finally:
        conn.close()


@pytest.fixture
def banco_pre_migracao(tmp_path):
    db_path = tmp_path / "media_variaveis.db"
    _rodar_alembic(db_path, "upgrade", REVISAO_ANTERIOR)
    return db_path


def test_cabeca_unica():
    """Duas cabeças = `upgrade head` ambíguo = API que não sobe e CI vermelha."""
    saida = _rodar_alembic(Path("/tmp/heads-check.db"), "heads")
    assert saida.count("(head)") == 1, saida


def test_upgrade_cria_as_oito_colunas(banco_pre_migracao):
    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = _colunas(banco_pre_migracao, tabela)
        for coluna in colunas:
            assert coluna not in existentes, f"{tabela}.{coluna} não deveria existir antes da migração"

    _rodar_alembic(banco_pre_migracao, "upgrade", REVISAO)

    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = _colunas(banco_pre_migracao, tabela)
        for coluna in colunas:
            assert coluna in existentes, f"{tabela}.{coluna} não foi criada"


def test_upgrade_e_idempotente_com_as_colunas_ja_criadas(banco_pre_migracao):
    """O cenário REAL de deploy: `create_all` do boot já criou as colunas e
    só depois o `upgrade head` roda. Sem o `sa.inspect` antes do `add_column`,
    é aqui que a API deixa de subir."""
    conn = sqlite3.connect(banco_pre_migracao)
    for tabela, colunas in COLUNAS_NOVAS.items():
        for coluna in colunas:
            tipo = "VARCHAR" if coluna.endswith("_composicao") else "FLOAT"
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    conn.commit()
    conn.close()

    _rodar_alembic(banco_pre_migracao, "upgrade", REVISAO)  # não pode abortar

    for tabela, colunas in COLUNAS_NOVAS.items():
        existentes = _colunas(banco_pre_migracao, tabela)
        assert set(colunas) <= existentes


def test_nenhum_backfill_o_registro_antigo_fica_com_media_nula(banco_pre_migracao):
    """Um 13º e umas férias já pagos, lançados ANTES da feature, não podem
    mudar de valor nem ganhar média nenhuma. Dinheiro que já saiu não muda de
    número retroativamente porque uma coluna nova entrou."""
    conn = sqlite3.connect(banco_pre_migracao)
    conn.execute(
        "INSERT INTO pessoa (nome, tipo, ativo, criado_em, salario_base) VALUES (?,?,?,?,?)",
        ("Leomir Bonfim", "Funcionário", 1, "2026-01-05 10:00:00", 3000.0),
    )
    pessoa_id = conn.execute("SELECT id FROM pessoa").fetchone()[0]
    conn.execute(
        "INSERT INTO ferias_funcionario "
        "(pessoa_id, periodo_aquisitivo_inicio, periodo_aquisitivo_fim, dias_direito, dias_gozados, "
        " data_inicio_gozo, data_fim_gozo, abono_pecuniario_dias, salario_base, valor_ferias, "
        " valor_terco_constitucional, valor_abono, valor_total, status, criado_em, centro_custo) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            pessoa_id, "2025-01-10", "2026-01-10", 30, 30, "2026-02-01", "2026-03-02", 0,
            3000.0, 3000.0, 999.9, 0.0, 3999.9, "pago", "2026-01-20 10:00:00", "Pecuária Leiteira",
        ),
    )
    conn.execute(
        "INSERT INTO decimo_terceiro "
        "(pessoa_id, ano, parcela, meses_trabalhados, salario_base, valor_integral, valor_bruto, "
        " valor_inss, valor_ir, valor_liquido, status, criado_em, centro_custo) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pessoa_id, 2025, "unica", 12, 3000.0, 3000.0, 3000.0, 0.0, 0.0, 3000.0, "pago",
         "2025-12-20 10:00:00", "Pecuária Leiteira"),
    )
    conn.commit()
    conn.close()

    _rodar_alembic(banco_pre_migracao, "upgrade", REVISAO)

    conn = sqlite3.connect(banco_pre_migracao)
    try:
        total, media, composicao = conn.execute(
            "SELECT valor_total, media_variaveis, media_variaveis_composicao FROM ferias_funcionario"
        ).fetchone()
        assert total == 3999.9
        assert media is None and composicao is None

        integral, media13, comp13 = conn.execute(
            "SELECT valor_integral, media_variaveis, media_variaveis_composicao FROM decimo_terceiro"
        ).fetchone()
        assert integral == 3000.0
        assert media13 is None and comp13 is None
    finally:
        conn.close()


def test_downgrade_remove_as_colunas_e_nao_mexe_no_dinheiro(banco_pre_migracao):
    """O que o downgrade tira é a CONFERÊNCIA (a composição), não o dinheiro:
    o valor lançado mora em colunas próprias e continua o que foi lançado."""
    _rodar_alembic(banco_pre_migracao, "upgrade", REVISAO)
    conn = sqlite3.connect(banco_pre_migracao)
    conn.execute(
        "INSERT INTO pessoa (nome, tipo, ativo, criado_em, salario_base) VALUES (?,?,?,?,?)",
        ("Leomir Bonfim", "Funcionário", 1, "2026-01-05 10:00:00", 3000.0),
    )
    pessoa_id = conn.execute("SELECT id FROM pessoa").fetchone()[0]
    conn.execute(
        "INSERT INTO decimo_terceiro "
        "(pessoa_id, ano, parcela, meses_trabalhados, salario_base, media_variaveis, valor_integral, "
        " valor_bruto, valor_inss, valor_ir, valor_liquido, status, criado_em, centro_custo) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pessoa_id, 2026, "unica", 12, 3000.0, 600.0, 3600.0, 3600.0, 0.0, 0.0, 3600.0, "pendente",
         "2026-12-20 10:00:00", "Pecuária Leiteira"),
    )
    conn.commit()
    conn.close()

    _rodar_alembic(banco_pre_migracao, "downgrade", REVISAO_ANTERIOR)

    conn = sqlite3.connect(banco_pre_migracao)
    try:
        assert "media_variaveis" not in _colunas(banco_pre_migracao, "decimo_terceiro")
        assert conn.execute("SELECT valor_integral FROM decimo_terceiro").fetchone()[0] == 3600.0
    finally:
        conn.close()
