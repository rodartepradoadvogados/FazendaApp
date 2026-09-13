"""
Testes de fazenda/rules/custo_leite.py (Custo por litro de leite) — módulo
sem teste dedicado até aqui, apesar de ser usado pelo endpoint
GET /financeiro/custo-litro-leite. Cobre a projeção proporcional por dia
quando o período não bate exatamente com o mês fechado da entrega.
"""
from __future__ import annotations

from datetime import date

from fazenda.rules.custo_leite import calcular_custo_por_litro, litros_leite_no_periodo


class TestLitrosLeiteNoPeriodo:
    def test_periodo_bate_exatamente_com_o_mes_inteiro(self):
        # Julho/2026 tem 31 dias — período = mês inteiro, sem projeção.
        litros = litros_leite_no_periodo(
            {"2026-07": 3100.0}, date(2026, 7, 1), date(2026, 7, 31),
        )
        assert litros == 3100.0

    def test_periodo_parcial_projeta_proporcional_aos_dias(self):
        # Julho/2026 (31 dias): 10 dias do período -> 10/31 da entrega do mês.
        litros = litros_leite_no_periodo(
            {"2026-07": 3100.0}, date(2026, 7, 1), date(2026, 7, 10),
        )
        assert round(litros, 2) == round(3100.0 / 31 * 10, 2)

    def test_periodo_cruzando_dois_meses_soma_a_projecao_de_cada_um(self):
        # Últimos 5 dias de julho (31 dias) + primeiros 3 dias de agosto (31 dias).
        litros = litros_leite_no_periodo(
            {"2026-07": 3100.0, "2026-08": 3200.0}, date(2026, 7, 27), date(2026, 8, 3),
        )
        esperado = (3100.0 / 31 * 5) + (3200.0 / 31 * 3)
        assert round(litros, 2) == round(esperado, 2)

    def test_competencia_sem_entrega_registrada_e_ignorada_sem_erro(self):
        litros = litros_leite_no_periodo({}, date(2026, 7, 1), date(2026, 7, 31))
        assert litros == 0.0

    def test_mes_com_29_dias_fevereiro_bissexto(self):
        # 2028 é bissexto — fevereiro tem 29 dias.
        litros = litros_leite_no_periodo(
            {"2028-02": 2900.0}, date(2028, 2, 1), date(2028, 2, 29),
        )
        assert litros == 2900.0


class TestCalcularCustoPorLitro:
    def test_divide_custo_pelos_litros(self):
        r = calcular_custo_por_litro(custo_total=3100.0, litros=1000.0)
        assert r == {"litros": 1000.0, "custo_total": 3100.0, "custo_por_litro": 3.1}

    def test_zero_litros_nao_divide_por_zero(self):
        r = calcular_custo_por_litro(custo_total=500.0, litros=0.0)
        assert r["custo_por_litro"] is None
        assert r["custo_total"] == 500.0

    def test_arredonda_custo_por_litro_em_4_casas(self):
        r = calcular_custo_por_litro(custo_total=1000.0, litros=3.0)
        assert r["custo_por_litro"] == round(1000.0 / 3.0, 4)
