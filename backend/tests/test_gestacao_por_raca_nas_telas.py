"""
Gestação por raça nas telas que antes usavam um valor FIXO.

A Agenda e as Listas de manejo sempre respeitaram a raça (280 Holandês /
287 Girolando / 295 Gir-Zebu, ver rules/gestation.py), mas três telas fixavam
um número só — ficha do animal e estado reprodutivo em 280, partos previstos
dos Indicadores em 288. Para um Gir isso previa o parto 15 dias antes do real,
e arrastava junto a previsão de secagem e a entrada no pré-parto.

Regra desta correção: a raça manda quando ela é CONHECIDA. Animal sem raça
cadastrada mantém exatamente o padrão anterior de cada tela — trocar isso
seria uma mudança de comportamento que ninguém pediu (ver
`dias_gestacao_da_raca`).
"""
from __future__ import annotations

from fazenda.rules.gestation import dias_gestacao_da_raca


class TestRacaConhecidaMandaNoCalculo:
    def test_holandes_280(self):
        assert dias_gestacao_da_raca("Holandês", 999) == 280

    def test_girolando_287(self):
        assert dias_gestacao_da_raca("Girolando", 999) == 287

    def test_gir_295(self):
        assert dias_gestacao_da_raca("Gir", 999) == 295

    def test_zebu_295(self):
        assert dias_gestacao_da_raca("Zebu", 999) == 295

    def test_girolando_nao_e_confundido_com_gir(self):
        # "gir" é substring de "girolando" — a ordem do dict garante que
        # Girolando (287) seja testado antes de Gir (295).
        assert dias_gestacao_da_raca("girolando 5/8", 999) == 287

    def test_case_e_espaco_nao_importam(self):
        assert dias_gestacao_da_raca("  HOLANDES  ", 999) == 280


class TestRacaDesconhecidaMantemOPadraoDaTela:
    def test_sem_raca_usa_o_padrao_recebido(self):
        assert dias_gestacao_da_raca(None, 280) == 280
        assert dias_gestacao_da_raca("", 288) == 288

    def test_raca_fora_do_mapa_usa_o_padrao_recebido(self):
        # Jersey não está no mapa — a tela mantém o número que já usava.
        assert dias_gestacao_da_raca("Jersey", 280) == 280


class TestImpactoReal:
    def test_gir_pare_15_dias_depois_do_holandes(self):
        # É este delta que fazia a fazenda secar e mover para o pré-parto
        # quinze dias cedo demais um animal Gir.
        assert dias_gestacao_da_raca("Gir", 280) - dias_gestacao_da_raca("Holandês", 280) == 15
