"""Janelas de lactação (`rules/lactacao.py`) — o "aberta ou fechada" que o
equivalente maduro usa para decidir quais lactações entram no cálculo dos
fatores de classe (só as encerradas) e qual é a lactação atual do animal."""
from __future__ import annotations

from datetime import date

from fazenda.rules.lactacao import JanelaLactacao, montar_janelas


class TestMontarJanelas:
    def test_parto_seguinte_encerra_a_lactacao(self):
        janelas = montar_janelas([date(2022, 1, 1), date(2023, 1, 1)], [])
        assert janelas == [
            JanelaLactacao(date(2022, 1, 1), date(2023, 1, 1), encerrada=True),
            JanelaLactacao(date(2023, 1, 1), None, encerrada=False),
        ]

    def test_secagem_encerra_quando_nao_ha_parto_seguinte(self):
        janelas = montar_janelas([date(2023, 1, 1)], [date(2023, 10, 1)])
        assert janelas == [JanelaLactacao(date(2023, 1, 1), date(2023, 10, 1), encerrada=True)]

    def test_sem_parto_seguinte_e_sem_secagem_fica_em_andamento(self):
        janelas = montar_janelas([date(2023, 1, 1)], [])
        assert janelas == [JanelaLactacao(date(2023, 1, 1), None, encerrada=False)]

    def test_secagem_anterior_ao_parto_e_ignorada(self):
        """Secagem de uma lactação ANTERIOR não pode encerrar esta — só
        secagens a partir do início da janela contam."""
        janelas = montar_janelas([date(2023, 1, 1)], [date(2022, 6, 1)])
        assert janelas[0].data_fim is None
        assert janelas[0].encerrada is False

    def test_parto_seguinte_tem_prioridade_sobre_secagem(self):
        """Quando existem os dois, o parto seguinte é quem encerra — a
        secagem pode ter sido tardia/mal lançada, o parto é o evento
        inequívoco."""
        janelas = montar_janelas(
            [date(2023, 1, 1), date(2024, 3, 1)],
            [date(2023, 11, 1)],
        )
        assert janelas[0].data_fim == date(2024, 3, 1)

    def test_ordem_de_entrada_nao_importa(self):
        """A função ordena por conta própria — partos e secagens podem vir
        em qualquer ordem."""
        janelas = montar_janelas(
            [date(2023, 1, 1), date(2021, 1, 1), date(2022, 1, 1)],
            [],
        )
        assert [j.data_inicio for j in janelas] == [date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1)]

    def test_sem_partos_nao_gera_janela(self):
        assert montar_janelas([], [date(2023, 1, 1)]) == []
