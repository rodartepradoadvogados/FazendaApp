"""
Resultado por litro (Fase B dos Relatórios) — `GET /financeiro/resultado-por-litro`
e o motor puro fazenda/rules/resultado_litro.py.

O endpoint só reparte por litro o que a DRE do servidor já mostra: os testes de
cenário conferem que COE, COT e o resultado saem das MESMAS linhas da cascata
de `GET /financeiro/dre` (mesmo período, regime e centro), com a flag
`financeiro_regras_v2` ligada e desligada.
"""
from __future__ import annotations

from datetime import date

import pytest

from fazenda.rules.resultado_litro import indicadores_por_litro, meses_da_serie, meses_no_periodo
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário da auditoria)

LINHAS = {
    "RECEITA_VENDAS": 12000.0, "DEDUCAO_IMPOSTOS": 200.0, "RECEITA_LIQUIDA": 11800.0,
    "CUSTO_VARIAVEL": 4000.0, "DESPESA_VARIAVEL": 1000.0, "GASTOS_PESSOAL": 2000.0,
    "DESPESAS_OPERACIONAIS": 1500.0, "DEPRECIACAO_AMORT_EXAUSTAO": 500.0, "RESULTADO_LIQUIDO": 2800.0,
}
LEITE = {"receita_leite": 10000.0, "deducoes_receita_leite": 200.0, "receita_leite_liquida": 9800.0, "custo_alimentacao": 3500.0}


def test_meses_no_periodo_conta_fracao_por_dia():
    assert meses_no_periodo(date(2031, 3, 1), date(2031, 3, 31)) == 1.0
    assert meses_no_periodo(date(2031, 1, 1), date(2031, 3, 31)) == 3.0
    assert meses_no_periodo(date(2031, 4, 1), date(2031, 4, 15)) == 0.5
    assert meses_no_periodo(date(2031, 4, 2), date(2031, 4, 1)) == 0.0


def test_meses_da_serie_termina_no_mes_do_fim_e_vira_o_ano():
    serie = meses_da_serie(date(2031, 2, 10), 3)
    assert serie == [
        (date(2030, 12, 1), date(2030, 12, 31)),
        (date(2031, 1, 1), date(2031, 1, 31)),
        (date(2031, 2, 1), date(2031, 2, 28)),
    ]
    assert meses_da_serie(date(2031, 2, 10), 0) == []


def test_indicadores_por_litro_coe_cot_margem_e_ponto_de_equilibrio():
    i = indicadores_por_litro(linhas=LINHAS, leite=LEITE, litros=5000.0, meses=1.0)
    # COE = variável (4.000 + 1.000) + pessoal 2.000 + operacionais 1.500; COT soma a depreciação.
    assert (i["coe"], i["cot"], i["depreciacao"]) == (8500.0, 9000.0, 500.0)
    assert (i["preco_bruto_l"], i["preco_liquido_l"]) == (2.0, 1.96)
    assert (i["coe_l"], i["cot_l"]) == (1.7, 1.8)
    assert i["margem_l"] == 0.26 and i["margem_cot_l"] == 0.16
    # (9.800 − 8.500) ÷ 9.800
    assert i["margem_pct"] == 13.3
    # Repartição do custeio: comida (contas do RMCA) + gente (pessoal) + outros = COE.
    assert round(i["comida"] + i["pessoal"] + i["outros_custeio"], 2) == i["coe"]
    # Fixos 4.000 (pessoal + operacionais + depreciação) ÷ (1,96 − 1,00 variável/L) = 4.166,67 L.
    pe = i["ponto_equilibrio"]
    assert pe["litros_periodo"] == 4167.0 and pe["litros_mes"] == 4167.0
    assert pe["contribuicao_por_litro"] == 0.96
    assert pe["folga_pct"] == 20.0
    assert i["resultado_liquido_dre"] == 2800.0


def test_indicadores_sem_litros_nao_inventam_numero():
    i = indicadores_por_litro(linhas=LINHAS, leite=LEITE, litros=0.0, meses=1.0)
    for chave in ("preco_liquido_l", "coe_l", "cot_l", "margem_l", "ponto_equilibrio"):
        assert i[chave] is None, chave
    assert i["coe"] == 8500.0  # o custo do período continua lá
    sem_receita = indicadores_por_litro(linhas={}, leite={}, litros=100.0, meses=1.0)
    assert sem_receita["margem_pct"] is None and sem_receita["ponto_equilibrio"] is None


def _linhas(dre: dict) -> dict:
    return {x["chave"]: x["valor"] for x in dre["cascata"]}


@pytest.mark.parametrize("ligar", [False, True])
def test_endpoint_reparte_a_mesma_dre_do_servidor(cenario, ligar):  # noqa: F811
    if ligar:
        cenario.ligar_regras_v2()
    mar = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}
    for regime in ("competencia", "caixa"):
        r = cenario.get("/financeiro/resultado-por-litro", **mar, regime=regime, centro_custo="Pecuária Leiteira")
        dre = cenario.get("/financeiro/dre", **mar, regime=regime, centro_custo="Pecuária Leiteira")
        linhas, a = _linhas(dre), r["atual"]
        coe = sum(linhas[k] for k in ("CUSTO_VARIAVEL", "DESPESA_VARIAVEL", "GASTOS_PESSOAL", "DESPESAS_OPERACIONAIS"))
        assert a["coe"] == round(coe, 2)
        assert a["cot"] == round(coe + linhas["DEPRECIACAO_AMORT_EXAUSTAO"], 2)
        assert a["resultado_liquido_dre"] == linhas["RESULTADO_LIQUIDO"]
        assert r["regras_v2"] is ligar and r["regime"] == regime
    assert r["configuracao"]["contas_leite"] == ["AUD Venda de leite"]
    assert r["configuracao"]["tem_entrega"] is True


def test_endpoint_litros_seguem_a_flag(cenario):  # noqa: F811
    mar = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}
    antes = cenario.get("/financeiro/resultado-por-litro", **mar)["atual"]
    # Flag desligada: a entrega de 10.320 kg conta como litro (como o custo por litro antigo).
    assert antes["litros"] == 10320.0
    cenario.ligar_regras_v2()
    depois = cenario.get("/financeiro/resultado-por-litro", **mar)
    a = depois["atual"]
    # Regras v2 (PR 4): 10.320 kg ÷ 1,029 — o mesmo litro do custo por litro e do RMCA.
    cl = cenario.get("/financeiro/custo-litro-leite", **mar)
    assert a["litros"] == cl["litros"] == 10029.2
    # Receita BRUTA do leite (10.000) com o Funrural/Senar da nota (150) em deduções, como o RMCA.
    rmca = cenario.get("/financeiro/rmca", **mar)["gerencial"]
    assert (a["receita_leite_bruta"], a["deducoes_leite"], a["receita_leite_liquida"]) == (
        rmca["receita_leite"], rmca["deducoes_receita_leite"], rmca["receita_leite_liquida"])
    assert a["preco_liquido_l"] == round(a["receita_leite_liquida"] / a["litros"], 4)
    assert any("convertida para litros" in x for x in depois["avisos"])


def test_endpoint_serie_de_meses_fechados(cenario):  # noqa: F811
    cenario.ligar_regras_v2()
    r = cenario.get("/financeiro/resultado-por-litro", data_inicio="2031-03-01", data_fim="2031-03-31", serie_meses=3)
    assert [m["competencia"] for m in r["serie"]] == ["2031-01", "2031-02", "2031-03"]
    jan, mar = r["serie"][0], r["serie"][-1]
    assert jan["litros"] == 0.0 and jan["coe_l"] is None and jan["margem_l"] is None
    assert mar["coe"] == r["atual"]["coe"] and mar["litros"] == r["atual"]["litros"]


def test_endpoint_recusa_periodo_invertido_e_regime_desconhecido(cenario):  # noqa: F811
    r = cenario.c.get("/financeiro/resultado-por-litro", params={"data_inicio": "2031-03-31", "data_fim": "2031-03-01"})
    assert r.status_code == 422
    r = cenario.c.get("/financeiro/resultado-por-litro", params={"data_inicio": "2031-03-01", "data_fim": "2031-03-31", "regime": "x"})
    assert r.status_code == 422
