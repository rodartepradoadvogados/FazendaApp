"""
Migração b2f7c1a83d59 — congelamento da discriminação do holerite no
pagamento da folha (C7), e o backfill das folhas já pagas.

O que o backfill FAZ: remonta, para cada folha já `pago`, a discriminação com
os dados que existem HOJE (o lançamento, as `vale_parcela` da competência, o
`vale_funcionario` de cada parcela e a nota fiscal de origem) e grava a
fotografia. A partir daí o recibo daquela folha para de se mexer.

O que ele NÃO consegue recuperar — e é isso que estes testes travam, porque é
a parte fácil de fingir:
- a discriminação de hoje pode já não ser a do DIA DO PAGAMENTO (não existe
  histórico de `vale_parcela`);
- por consequência, uma folha paga que JÁ ESTÁ divergente continua divergente
  depois da migração: nada de `valor_liquido`, `valor_vale`, status ou conta a
  pagar é reescrito. As duas alternativas seriam mentir — reescrever dinheiro
  que já saiu, ou forjar linhas que fechassem a conta num documento
  trabalhista.

Mesma técnica de subprocesso das demais migrações (ver
test_migracao_ferias_decimo_snapshot.py).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REVISAO_ANTERIOR = "e0b7c3a91d24"


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
    db_path = tmp_path / "folha_congelada.db"
    _rodar_alembic(db_path, "upgrade", REVISAO_ANTERIOR)
    return db_path


def _inserir(db_path: Path, tabela: str, **campos) -> int:
    conn = sqlite3.connect(db_path)
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    cur = conn.execute(f"INSERT INTO {tabela} ({colunas}) VALUES ({marcas})", tuple(campos.values()))
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def _pessoa(db_path: Path, nome: str = "Leomir Bonfim", **campos) -> int:
    return _inserir(
        db_path, "pessoa", nome=nome, tipo="Funcionário", ativo=1,
        criado_em="2026-01-05 10:00:00", salario_base=3200.0, **campos,
    )


def _folha(db_path: Path, pessoa_id: int, **campos) -> int:
    base = {
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        "descontos": 0.0, "percentual_inss": 0.0, "percentual_ir": 0.0,
        "valor_inss": 0.0, "valor_ir": 0.0, "valor_vale": 0.0, "valor_liquido": 3200.0,
        "status": "pago", "recorrente": 0, "centro_custo": "Pecuária Leiteira",
        "criado_em": "2026-07-01 10:00:00",
    }
    base.update(campos)
    return _inserir(db_path, "folha_pagamento", **base)


def _vale(db_path: Path, pessoa_id: int, **campos) -> int:
    base = {
        "pessoa_id": pessoa_id, "valor_total": 400.0, "forma_pagamento": "pix",
        "data_pagamento": "2026-06-10", "parcelas": 1, "competencia_inicio": "2026-07",
        "observacao": "mercado", "criado_em": "2026-06-10 10:00:00",
    }
    base.update(campos)
    return _inserir(db_path, "vale_funcionario", **base)


def _parcela(db_path: Path, vale_id: int, pessoa_id: int, **campos) -> int:
    base = {
        "vale_id": vale_id, "pessoa_id": pessoa_id, "competencia": "2026-07",
        "valor": 400.0, "aplicada": 1, "criado_em": "2026-06-10 10:00:00",
    }
    base.update(campos)
    return _inserir(db_path, "vale_parcela", **base)


def _ler(db_path: Path, tabela: str, registro_id: int, coluna: str):
    conn = sqlite3.connect(db_path)
    valor = conn.execute(f"SELECT {coluna} FROM {tabela} WHERE id = ?", (registro_id,)).fetchone()[0]
    conn.close()
    return valor


def _linhas(db_path: Path, folha_id: int) -> list[dict]:
    bruto = _ler(db_path, "folha_pagamento", folha_id, "discriminacao_congelada")
    assert bruto is not None, "folha paga ficou sem fotografia"
    return json.loads(bruto)


class TestColunasNovas:
    def test_as_duas_colunas_passam_a_existir(self, banco_pre_migracao):
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        conn = sqlite3.connect(banco_pre_migracao)
        colunas = {c[1] for c in conn.execute("PRAGMA table_info(folha_pagamento)")}
        conn.close()
        assert {"discriminacao_congelada", "discriminacao_congelada_em"} <= colunas


class TestBackfill:
    def test_folha_paga_ganha_a_fotografia_do_recibo(self, banco_pre_migracao):
        pessoa_id = _pessoa(banco_pre_migracao)
        vale_id = _vale(banco_pre_migracao, pessoa_id)
        _parcela(banco_pre_migracao, vale_id, pessoa_id)
        folha_id = _folha(
            banco_pre_migracao, pessoa_id, valor_vale=400.0, valor_liquido=2551.04,
            percentual_inss=7.78, valor_inss=248.96,
        )
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        linhas = _linhas(banco_pre_migracao, folha_id)
        assert [l["tipo"] for l in linhas] == ["bruto", "inss", "vale", "liquido"]
        assert linhas[0]["referencia"] == "Mensal"
        assert linhas[1]["referencia"] == "7,78% sobre R$ 3.200,00"
        assert linhas[2]["descricao"] == "Vale — mercado"
        assert linhas[2]["referencia"] == "Parcela única · vale de 10/06/2026"
        assert linhas[2]["origem"]["vale_id"] == vale_id
        assert linhas[-1]["valor"] == 2551.04
        assert _ler(banco_pre_migracao, "folha_pagamento", folha_id, "discriminacao_congelada_em")

    def test_parcela_de_outra_competencia_so_numera_k_de_n(self, banco_pre_migracao):
        """O "3 de 13" vem da sequência COMPLETA do vale; as parcelas dos
        outros meses não viram linha do recibo desta competência."""
        pessoa_id = _pessoa(banco_pre_migracao)
        vale_id = _vale(banco_pre_migracao, pessoa_id, valor_total=900.0, parcelas=3)
        for competencia in ("2026-07", "2026-08", "2026-09"):
            _parcela(banco_pre_migracao, vale_id, pessoa_id, competencia=competencia, valor=300.0)
        folha_id = _folha(banco_pre_migracao, pessoa_id, competencia="2026-08", valor_vale=300.0, valor_liquido=2900.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        vales = [l for l in _linhas(banco_pre_migracao, folha_id) if l["tipo"] == "vale"]
        assert len(vales) == 1
        assert vales[0]["referencia"] == "Parcela 2 de 3 · vale de 10/06/2026"
        assert vales[0]["label"] == "Vale (parcela 2/3)"

    def test_nota_fiscal_de_origem_entra_na_descricao(self, banco_pre_migracao):
        pessoa_id = _pessoa(banco_pre_migracao)
        vale_id = _vale(banco_pre_migracao, pessoa_id, observacao=None)
        _parcela(banco_pre_migracao, vale_id, pessoa_id)
        _inserir(
            banco_pre_migracao, "conta_gerencial", numero_lancamento="LC-2026-0007",
            parcela_num=1, fornecedor_cliente="Auto Peças", numero_nota="4471",
            data_emissao="2026-06-09", atualizado_em="2026-06-09 10:00:00",
        )
        _inserir(
            banco_pre_migracao, "lancamento_item", numero_lancamento="LC-2026-0007",
            produto="Kit embreagem", valor_total=400.0, vale_funcionario_id=vale_id,
            atualizado_em="2026-06-09 10:00:00",
        )
        folha_id = _folha(banco_pre_migracao, pessoa_id, valor_vale=400.0, valor_liquido=2800.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        vale = [l for l in _linhas(banco_pre_migracao, folha_id) if l["tipo"] == "vale"][0]
        assert vale["descricao"] == "Vale — nota 4471 (Kit embreagem)"
        assert vale["origem"]["origem_lancamento"]["numero_documento"] == "4471"

    def test_mes_de_admissao_mantem_a_referencia_proporcional(self, banco_pre_migracao):
        pessoa_id = _pessoa(banco_pre_migracao, data_admissao="2026-07-16")
        folha_id = _folha(banco_pre_migracao, pessoa_id, valor_bruto=1600.0, valor_liquido=1600.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        assert _linhas(banco_pre_migracao, folha_id)[0]["referencia"] == (
            "Admissão em 16/07 · 16 de 31 dias do mês"
        )

    def test_folha_pendente_nao_e_congelada(self, banco_pre_migracao):
        """Folha não paga continua sendo calculada ao vivo — congelá-la
        travaria os self-heals que ainda precisam agir sobre ela."""
        pessoa_id = _pessoa(banco_pre_migracao)
        folha_id = _folha(banco_pre_migracao, pessoa_id, status="pendente")
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        assert _ler(banco_pre_migracao, "folha_pagamento", folha_id, "discriminacao_congelada") is None
        assert _ler(banco_pre_migracao, "folha_pagamento", folha_id, "discriminacao_congelada_em") is None

    def test_banco_sem_folha_paga_nenhuma_nao_explode(self, banco_pre_migracao):
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        conn = sqlite3.connect(banco_pre_migracao)
        assert conn.execute("SELECT COUNT(*) FROM folha_pagamento").fetchone()[0] == 0
        conn.close()


class TestLimitesAssumidosDoBackfill:
    def test_nenhum_valor_gravado_da_folha_paga_e_reescrito(self, banco_pre_migracao):
        """A migração só grava as duas colunas novas. Líquido, vale, status e
        data de pagamento ficam exatamente como estavam."""
        pessoa_id = _pessoa(banco_pre_migracao)
        vale_id = _vale(banco_pre_migracao, pessoa_id)
        _parcela(banco_pre_migracao, vale_id, pessoa_id)
        folha_id = _folha(
            banco_pre_migracao, pessoa_id, valor_vale=400.0, valor_liquido=2800.0,
            data_pagamento="2026-08-05",
        )
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        for coluna, esperado in (
            ("valor_liquido", 2800.0), ("valor_vale", 400.0), ("valor_bruto", 3200.0),
            ("status", "pago"), ("data_pagamento", "2026-08-05"),
        ):
            assert _ler(banco_pre_migracao, "folha_pagamento", folha_id, coluna) == esperado

    def test_folha_paga_que_ja_esta_divergente_continua_divergente(self, banco_pre_migracao):
        """LIMITE DELIBERADO E DECLARADO. O vale foi lançado depois do
        pagamento (é o próprio defeito C7 acontecendo em produção): o líquido
        gravado é de antes dele, a discriminação de hoje já o inclui. A
        migração congela o que existe HOJE — não tem como saber qual era o
        recibo do dia do pagamento — e NÃO fecha a conta por cima.

        Fechar significaria mentir de um dos dois jeitos: reescrever
        `valor_liquido` (dinheiro que já saiu) ou apagar a linha do vale
        (forjar um documento trabalhista). A divergência fica visível na tela
        ("Recibo não soma o líquido pago") para conferência humana — é decisão
        do dono, lançamento a lançamento."""
        pessoa_id = _pessoa(banco_pre_migracao)
        vale_id = _vale(banco_pre_migracao, pessoa_id, valor_total=500.0)
        _parcela(banco_pre_migracao, vale_id, pessoa_id, valor=500.0)
        # Líquido gravado de um pagamento que NÃO descontou este vale.
        folha_id = _folha(banco_pre_migracao, pessoa_id, valor_vale=0.0, valor_liquido=3200.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        linhas = _linhas(banco_pre_migracao, folha_id)
        soma = round(
            sum(l["provento"] or 0 for l in linhas if l["tipo"] != "liquido")
            - sum(l["desconto"] or 0 for l in linhas if l["tipo"] != "liquido"), 2,
        )
        assert soma == 2700.0
        assert _ler(banco_pre_migracao, "folha_pagamento", folha_id, "valor_liquido") == 3200.0
        assert abs(soma - 3200.0) > 0.01, "a divergência preexistente tem de continuar visível"

    def test_vale_excluido_depois_do_pagamento_nao_deixa_rastro_a_congelar(self, banco_pre_migracao):
        """Sem `vale_parcela`, não há linha para reconstruir — e o líquido
        gravado (que descontava o vale) continua onde está."""
        pessoa_id = _pessoa(banco_pre_migracao)
        folha_id = _folha(banco_pre_migracao, pessoa_id, valor_vale=400.0, valor_liquido=2800.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        linhas = _linhas(banco_pre_migracao, folha_id)
        assert [l["tipo"] for l in linhas] == ["bruto", "liquido"]
        assert _ler(banco_pre_migracao, "folha_pagamento", folha_id, "valor_liquido") == 2800.0


class TestDowngrade:
    def test_downgrade_remove_as_duas_colunas(self, banco_pre_migracao):
        pessoa_id = _pessoa(banco_pre_migracao)
        vale_id = _vale(banco_pre_migracao, pessoa_id)
        _parcela(banco_pre_migracao, vale_id, pessoa_id)
        _folha(banco_pre_migracao, pessoa_id, valor_vale=400.0, valor_liquido=2800.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        _rodar_alembic(banco_pre_migracao, "downgrade", REVISAO_ANTERIOR)

        conn = sqlite3.connect(banco_pre_migracao)
        colunas = {c[1] for c in conn.execute("PRAGMA table_info(folha_pagamento)")}
        # A folha em si sobrevive intacta ao ida-e-volta.
        assert conn.execute("SELECT valor_liquido FROM folha_pagamento").fetchone()[0] == 2800.0
        conn.close()
        assert "discriminacao_congelada" not in colunas
        assert "discriminacao_congelada_em" not in colunas

    def test_upgrade_de_novo_depois_do_downgrade_reconstroi_a_fotografia(self, banco_pre_migracao):
        pessoa_id = _pessoa(banco_pre_migracao)
        vale_id = _vale(banco_pre_migracao, pessoa_id)
        _parcela(banco_pre_migracao, vale_id, pessoa_id)
        folha_id = _folha(banco_pre_migracao, pessoa_id, valor_vale=400.0, valor_liquido=2800.0)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")
        _rodar_alembic(banco_pre_migracao, "downgrade", REVISAO_ANTERIOR)
        _rodar_alembic(banco_pre_migracao, "upgrade", "head")

        assert [l["tipo"] for l in _linhas(banco_pre_migracao, folha_id)] == ["bruto", "vale", "liquido"]
