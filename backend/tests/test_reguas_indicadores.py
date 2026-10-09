"""Réguas de referência: o número da FAZENDA de cada régua
(`GET /financeiro/reguas-referencia/indicadores-fazenda` e o motor puro
fazenda/rules/reguas_indicadores.py). Não é conta nova: sai das MESMAS linhas da
DRE e do Resultado por litro do servidor no mesmo período, regime e centro."""
from __future__ import annotations

import pytest

from fazenda.rules.reguas_indicadores import MOTIVOS_SEM_DADO, indicadores_da_fazenda
from fazenda.rules.resultado_litro import indicadores_por_litro
from tests.test_relatorios_cenario_auditoria import cenario  # noqa: F401  (fixture do cenário da auditoria)

LINHAS = {
    "RECEITA_VENDAS": 12000.0, "DEDUCAO_IMPOSTOS": 200.0, "RECEITA_LIQUIDA": 11800.0,
    "CUSTO_VARIAVEL": 4000.0, "DESPESA_VARIAVEL": 1000.0, "GASTOS_PESSOAL": 2000.0,
    "DESPESAS_OPERACIONAIS": 1500.0, "DEPRECIACAO_AMORT_EXAUSTAO": 500.0, "RESULTADO_LIQUIDO": 2800.0,
}
LEITE = {"receita_leite": 10000.0, "deducoes_receita_leite": 200.0, "receita_leite_liquida": 9800.0, "custo_alimentacao": 3500.0}


def test_indicadores_saem_das_linhas_da_dre_e_do_litro():
    litro = indicadores_por_litro(linhas=LINHAS, leite=LEITE, litros=5000.0, meses=1.0)
    i = indicadores_da_fazenda(litro=litro, linhas=LINHAS, saldo_caixa=17000.0)
    assert i["comida_receita"]["valor"] == 35.0  # 3.500 ÷ 10.000 (receita BRUTA do leite, como o RMCA)
    assert i["coe_receita"]["valor"] == 70.8  # COE 8.500 ÷ receita bruta 12.000
    assert i["mao_obra_receita"]["valor"] == 16.7  # pessoal 2.000 ÷ 12.000
    assert i["depreciacao_cot"]["valor"] == 5.6  # 500 ÷ COT 9.000
    assert i["coe_litro_reais"]["valor"] == 1.7
    assert i["reserva_caixa"]["valor"] == 2.0  # 17.000 ÷ (8.500 por mês)
    assert i["comida_receita"]["conta"] == "Alimentação R$ 3.500,00 ÷ receita do leite R$ 10.000,00"
    assert i["coe_litro_reais"]["conta"] == "Custeio (COE) R$ 8.500,00 ÷ 5.000 L entregues"
    assert i["comida_receita"]["relatorio"] == "rmca" and i["coe_receita"]["relatorio"] == "rel_dre"
    # Integração da Fase C: o link vai ao item da árvore (o Caixa real no molde), não ao id antigo.
    assert i["reserva_caixa"]["relatorio"] == "rel_caixa"
    for codigo in MOTIVOS_SEM_DADO:
        assert i[codigo]["valor"] is None and i[codigo]["motivo"], codigo


def test_sem_divisor_ou_sem_caixa_nao_inventa_numero():
    litro = indicadores_por_litro(linhas={}, leite={}, litros=0.0, meses=1.0)
    i = indicadores_da_fazenda(litro=litro, linhas={}, saldo_caixa=None, motivo_saldo="só admin")
    for codigo, item in i.items():
        assert item["valor"] is None and item["conta"] is None and item["motivo"], codigo
    assert i["reserva_caixa"]["motivo"] == "só admin"


@pytest.mark.parametrize("ligar", [False, True])
def test_endpoint_usa_a_mesma_dre_e_o_mesmo_litro(cenario, ligar):  # noqa: F811
    if ligar:
        cenario.ligar_regras_v2()
    q = {"data_inicio": "2031-03-01", "data_fim": "2031-03-31"}
    conferidos = 0
    for regime in ("competencia", "caixa"):
        r = cenario.get("/financeiro/reguas-referencia/indicadores-fazenda", **q, regime=regime)
        litro = cenario.get("/financeiro/resultado-por-litro", **q, regime=regime)["atual"]
        dre = {x["chave"]: x["valor"] for x in cenario.get("/financeiro/dre", **q, regime=regime)["cascata"]}
        ind = r["indicadores"]
        assert r["regras_v2"] is ligar and r["regime"] == regime
        if dre["RECEITA_VENDAS"] > 0:
            assert ind["coe_receita"]["valor"] == round(100 * litro["coe"] / dre["RECEITA_VENDAS"], 1)
            conferidos += 1
        else:
            assert ind["coe_receita"]["valor"] is None
        if litro["receita_leite_bruta"] > 0:
            assert ind["comida_receita"]["valor"] == round(100 * litro["comida"] / litro["receita_leite_bruta"], 1)
            conferidos += 1
        assert ind["coe_litro_reais"]["valor"] == litro["coe_l"]
        # Administrador vê o caixa: a reserva usa o saldo de hoje do Caixa real (sem motivo de bloqueio).
        assert ind["reserva_caixa"]["motivo"] != "O saldo do caixa só aparece para o administrador da fazenda."
    assert conferidos >= 2  # o cenário tem receita em março: a conta foi de fato conferida


def test_endpoint_nao_devolve_faixa_e_recusa_periodo_invertido(cenario):  # noqa: F811
    r = cenario.get("/financeiro/reguas-referencia/indicadores-fazenda", data_inicio="2031-03-01", data_fim="2031-03-31")
    assert set(r) == {"periodo", "regime", "centro_custo", "regras_v2", "indicadores"}
    for item in r["indicadores"].values():
        assert set(item) == {"valor", "conta", "relatorio", "motivo"}
    ruim = cenario.c.get("/financeiro/reguas-referencia/indicadores-fazenda", params={"data_inicio": "2031-03-31", "data_fim": "2031-03-01"})
    assert ruim.status_code == 422
