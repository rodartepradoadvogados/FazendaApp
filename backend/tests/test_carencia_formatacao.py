"""
Campo único de carência: dois prazos configurados separados (leite e carne)
viram uma informação só na tela. O caso que mais importa é o do NULO — ele
tem que dizer "não informada", nunca "0 dias", que o operador leria como
liberado.
"""
from __future__ import annotations

from datetime import date

from fazenda.rules.carencia import carencia_dict, formatar_carencia


class TestFormatarCarencia:
    def test_so_leite(self):
        assert formatar_carencia(3, None) == "Carência: leite — 3 dias"

    def test_so_carne(self):
        assert formatar_carencia(None, 28) == "Carência: carne — 28 dias"

    def test_leite_e_carne(self):
        assert formatar_carencia(3, 28) == "Carência: leite — 3 dias / carne — 28 dias"

    def test_nenhum_informado_nunca_vira_zero(self):
        assert formatar_carencia(None, None) == "Carência: não informada"
        assert "0" not in formatar_carencia(None, None)

    def test_zero_dia_e_diferente_de_nao_informado(self):
        # Carência zero EXISTE (ex.: ceftiofur RTU para leite) e é uma
        # informação legítima da bula — não pode cair no "não informada".
        assert formatar_carencia(0, 3) == "Carência: leite — 0 dias / carne — 3 dias"

    def test_proibido_em_lactacao_ganha_do_prazo_de_leite(self):
        texto = formatar_carencia(None, 35, proibido_lactacao=True)
        assert texto == "Carência: leite — NÃO USAR em lactação / carne — 35 dias"

    def test_proibido_em_lactacao_sem_prazo_de_carne(self):
        assert formatar_carencia(None, None, proibido_lactacao=True) == "Carência: leite — NÃO USAR em lactação"


class TestCarenciaDict:
    def test_devolve_prazos_crus_e_texto_pronto(self):
        d = carencia_dict(3, 28)
        assert d["leite_dias"] == 3 and d["carne_dias"] == 28
        assert d["proibido_lactacao"] is False
        assert d["texto"] == "Carência: leite — 3 dias / carne — 28 dias"

    def test_com_data_calcula_a_liberacao(self):
        d = carencia_dict(3, 28, data_aplicacao=date(2026, 8, 7))
        assert d["liberacao_leite"] == "2026-08-10"
        assert d["liberacao_carne"] == "2026-09-04"

    def test_proibido_em_lactacao_nao_projeta_liberacao_de_leite(self):
        d = carencia_dict(None, 35, proibido_lactacao=True, data_aplicacao=date(2026, 8, 7))
        assert d["liberacao_leite"] is None
        assert d["liberacao_carne"] == "2026-09-11"

    def test_sem_data_nao_projeta_nada(self):
        d = carencia_dict(3, 28)
        assert d["liberacao_leite"] is None and d["liberacao_carne"] is None
