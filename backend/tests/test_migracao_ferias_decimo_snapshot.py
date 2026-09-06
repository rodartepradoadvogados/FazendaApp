"""
Migração e0b7c3a91d24 — colunas novas de `ferias_funcionario`/
`decimo_terceiro` (snapshot do salário, abono persistido, 13º integral,
`rescisao_id`) e o backfill de cada uma.

O backfill não inventa nada: reconstitui o salário pela INVERSÃO da própria
fórmula de cálculo e o abono pela diferença que já estava implícita no
`valor_total` gravado. O que ele deliberadamente NÃO faz — corrigir os 13º
já lançados em dobro — também é travado aqui: reescrever conta a pagar
(algumas já pagas) a partir de um palpite sobre qual linha o dono considerou
certa é decisão dele, na tela.

Mesma técnica de subprocesso das demais migrações (ver
test_migracao_fazenda_eh_teste.py).
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
    db_path = tmp_path / "ferias_decimo.db"
    _rodar_alembic(db_path, "upgrade", "d4a1f6c2b9e7")
    return db_path


def _inserir_ferias(db_path: Path, **campos) -> int:
    base = {
        "pessoa_id": 1,
        "periodo_aquisitivo_inicio": "2025-01-10", "periodo_aquisitivo_fim": "2026-01-10",
        "dias_direito": 30, "dias_gozados": 30,
        "data_inicio_gozo": "2026-07-01", "data_fim_gozo": "2026-07-30",
        "abono_pecuniario_dias": 0,
        "valor_ferias": 3000.0, "valor_terco_constitucional": 1000.0, "valor_total": 4000.0,
        "status": "pendente", "centro_custo": "Pecuária Leiteira",
        "criado_em": "2026-01-05 10:00:00",
    }
    base.update(campos)
    conn = sqlite3.connect(db_path)
    colunas = ", ".join(base)
    marcas = ", ".join("?" for _ in base)
    cur = conn.execute(f"INSERT INTO ferias_funcionario ({colunas}) VALUES ({marcas})", tuple(base.values()))
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def _inserir_decimo(db_path: Path, **campos) -> int:
    base = {
        "pessoa_id": 1, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        "valor_bruto": 3000.0, "valor_inss": 0.0, "valor_ir": 0.0, "valor_liquido": 3000.0,
        "status": "pendente", "centro_custo": "Pecuária Leiteira",
        "criado_em": "2026-01-05 10:00:00",
    }
    base.update(campos)
    conn = sqlite3.connect(db_path)
    colunas = ", ".join(base)
    marcas = ", ".join("?" for _ in base)
    cur = conn.execute(f"INSERT INTO decimo_terceiro ({colunas}) VALUES ({marcas})", tuple(base.values()))
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def _ler(db_path: Path, tabela: str, registro_id: int, coluna: str):
    conn = sqlite3.connect(db_path)
    valor = conn.execute(f"SELECT {coluna} FROM {tabela} WHERE id = ?", (registro_id,)).fetchone()[0]
    conn.close()
    return valor


class TestColunasNovas:
    def test_as_seis_colunas_passam_a_existir(self, banco_pre_migracao):
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        conn = sqlite3.connect(banco_pre_migracao)
        ferias = {c[1] for c in conn.execute("PRAGMA table_info(ferias_funcionario)")}
        decimo = {c[1] for c in conn.execute("PRAGMA table_info(decimo_terceiro)")}
        conn.close()
        assert {"salario_base", "valor_abono", "rescisao_id"} <= ferias
        assert {"salario_base", "valor_integral", "rescisao_id"} <= decimo


class TestBackfillFerias:
    def test_salario_reconstituido_pela_inversao_da_formula(self, banco_pre_migracao):
        """valor_ferias = salario/30 × dias_gozados — logo salario =
        valor_ferias × 30 / dias_gozados. 20 dias a R$ 2.000 => R$ 3.000."""
        registro = _inserir_ferias(
            banco_pre_migracao, dias_gozados=20, valor_ferias=2000.0,
            valor_terco_constitucional=666.6, valor_total=2666.6,
        )
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        assert _ler(banco_pre_migracao, "ferias_funcionario", registro, "salario_base") == 3000.0

    def test_abono_reconstituido_pela_diferenca(self, banco_pre_migracao):
        """Com abono, `valor_ferias + valor_terco != valor_total` no banco —
        a diferença sempre foi o abono, agora ela vira coluna."""
        registro = _inserir_ferias(
            banco_pre_migracao, dias_gozados=20, abono_pecuniario_dias=10,
            valor_ferias=2000.0, valor_terco_constitucional=666.6, valor_total=3999.9,
        )
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        assert _ler(banco_pre_migracao, "ferias_funcionario", registro, "valor_abono") == 1333.3

    def test_sem_abono_a_coluna_nasce_zerada_e_nao_com_ruido_de_centavo(self, banco_pre_migracao):
        """Somas antigas com 0,3333 deixam sobra de arredondamento; sem dias
        vendidos, isso não pode virar um "abono" de um centavo no recibo."""
        registro = _inserir_ferias(
            banco_pre_migracao, abono_pecuniario_dias=0,
            valor_ferias=3000.0, valor_terco_constitucional=999.9, valor_total=4000.0,
        )
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        assert _ler(banco_pre_migracao, "ferias_funcionario", registro, "valor_abono") == 0

    def test_dias_gozados_zerado_nao_explode_e_deixa_o_snapshot_nulo(self, banco_pre_migracao):
        registro = _inserir_ferias(banco_pre_migracao, dias_gozados=0, valor_ferias=0.0, valor_total=0.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        assert _ler(banco_pre_migracao, "ferias_funcionario", registro, "salario_base") is None


class TestBackfillDecimo:
    def test_valor_integral_recebe_o_que_ja_estava_gravado(self, banco_pre_migracao):
        registro = _inserir_decimo(banco_pre_migracao, valor_bruto=3000.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        assert _ler(banco_pre_migracao, "decimo_terceiro", registro, "valor_integral") == 3000.0

    def test_salario_reconstituido_pela_inversao_da_formula(self, banco_pre_migracao):
        registro = _inserir_decimo(
            banco_pre_migracao, meses_trabalhados=6, valor_bruto=1800.0, valor_liquido=1800.0,
        )
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        assert _ler(banco_pre_migracao, "decimo_terceiro", registro, "salario_base") == 3600.0

    def test_o_13o_ja_lancado_em_dobro_nao_e_reescrito_pela_migracao(self, banco_pre_migracao):
        """LIMITE DELIBERADO: as duas linhas de R$ 3.000 (1ª e 2ª parcela do
        bug) continuam valendo R$ 3.000 cada. Corrigir aqui reescreveria
        conta a pagar — inclusive já paga — a partir de uma suposição sobre
        qual delas o dono considerou certa. A migração só para a hemorragia
        daqui pra frente; o passado é decisão dele, lançamento a lançamento."""
        primeira = _inserir_decimo(banco_pre_migracao, parcela="primeira", valor_bruto=3000.0)
        segunda = _inserir_decimo(banco_pre_migracao, parcela="segunda", valor_bruto=3000.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        assert _ler(banco_pre_migracao, "decimo_terceiro", primeira, "valor_bruto") == 3000.0
        assert _ler(banco_pre_migracao, "decimo_terceiro", segunda, "valor_bruto") == 3000.0


class TestDowngrade:
    def test_downgrade_remove_as_colunas(self, banco_pre_migracao):
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        _rodar_alembic(banco_pre_migracao, "downgrade", "d4a1f6c2b9e7")
        conn = sqlite3.connect(banco_pre_migracao)
        ferias = {c[1] for c in conn.execute("PRAGMA table_info(ferias_funcionario)")}
        decimo = {c[1] for c in conn.execute("PRAGMA table_info(decimo_terceiro)")}
        conn.close()
        assert "salario_base" not in ferias and "valor_abono" not in ferias
        assert "valor_integral" not in decimo
