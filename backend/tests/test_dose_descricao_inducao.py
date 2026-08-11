"""
Dose no texto do card de indução de lactação — regressão de ago/2026.

O card da Agenda (site e app) mostrava DUAS doses diferentes para o mesmo
medicamento na mesma etapa: "3 ml Benzoato de Estradiol" no cabeçalho e
"Benzoato de Estradiol · 30ml" logo abaixo, no bloco do frasco. O bloco do
frasco lê a dose numérica do banco (30.0, correta); o cabeçalho lê
`ProtocoloInducaoAplicacao.descricao`, um texto gravado no lançamento por
`_descricao_medicamentos_dia`, que fazia `f"{dose:g}".rstrip("0")` — e o
rstrip comia o zero significativo de toda dose múltipla de 10.

Estes testes são sobre a função de formatação em si, sem subir aplicação:
é ela a fonte única do texto e é nela que o bug morava.
"""
from __future__ import annotations

import pytest

from fazenda.api.routers.producao import _descricao_medicamentos_dia
from fazenda.models.sanidade import ProtocoloInducaoLactacaoEtapa


def _etapa(produto: str, dose: float | None, unidade: str | None = "ml") -> ProtocoloInducaoLactacaoEtapa:
    return ProtocoloInducaoLactacaoEtapa(
        protocolo_id=1, dia=0, tipo="medicamento", produto=produto, dose=dose, unidade=unidade,
    )


@pytest.mark.parametrize(
    "dose,esperado",
    [
        # O caso do relato: o seed de "ATIVOS 1" manda 30 ml no D0-D6 e o
        # card mostrava 3 ml.
        (30.0, "30 ml Benzoato de Estradiol"),
        (20.0, "20 ml Benzoato de Estradiol"),
        (10.0, "10 ml Benzoato de Estradiol"),
        (100.0, "100 ml Benzoato de Estradiol"),
        # Doses que nunca quebraram — não podem regredir por causa da correção.
        (3.0, "3 ml Benzoato de Estradiol"),
        (2.5, "2.5 ml Benzoato de Estradiol"),
        (0.5, "0.5 ml Benzoato de Estradiol"),
    ],
)
def test_dose_multipla_de_dez_nao_perde_o_zero(dose, esperado):
    assert _descricao_medicamentos_dia([_etapa("Benzoato de Estradiol", dose)]) == esperado


def test_varios_medicamentos_no_mesmo_dia():
    etapas = [
        _etapa("Somatotropina Bovina (bST)", None, "dose"),
        _etapa("Benzoato de Estradiol", 20.0),
    ]
    assert _descricao_medicamentos_dia(etapas) == "Somatotropina Bovina (bST) + 20 ml Benzoato de Estradiol"


def test_dia_sem_medicamento():
    assert _descricao_medicamentos_dia([]) == "-"


def test_medicamento_sem_unidade_nao_sai_com_espaco_duplo():
    assert _descricao_medicamentos_dia([_etapa("Dexametasona", 10.0, None)]) == "10 Dexametasona"
