"""
Entrega de leite em kg ou em litro (1 L = 1,029 kg).

O controle leiteiro é sempre em kg. A entrega ao laticínio pode ser
contratada em kg ou em litro — e até aqui o litro entrava na comparação
Controle × Entregue como se fosse kg, inflando o "não entregue" (leite dos
bezerros + equipe) em ~2,9% do volume entregue.

kg continua sendo o padrão: lançamento sem unidade (todos os antigos) é lido
exatamente como antes, então nenhum número histórico muda.
"""
from __future__ import annotations

import pytest

from fazenda.rules.unidades import DENSIDADE_LEITE_KG_POR_L, leite_para_kg


class TestConversao:
    def test_kg_nao_converte(self):
        assert leite_para_kg(1000.0, "kg") == 1000.0

    def test_litro_vira_kg(self):
        assert leite_para_kg(1000.0, "L") == pytest.approx(1029.0)

    def test_densidade_e_a_pedida(self):
        assert DENSIDADE_LEITE_KG_POR_L == 1.029


class TestPadraoEhKg:
    def test_unidade_ausente_e_tratada_como_kg(self):
        # Lançamentos anteriores ao campo `unidade` — o sistema já os tratava
        # como kg na comparação, então continuam valendo o mesmo.
        assert leite_para_kg(1000.0, None) == 1000.0

    def test_unidade_vazia_e_tratada_como_kg(self):
        assert leite_para_kg(1000.0, "") == 1000.0

    def test_unidade_desconhecida_cai_em_kg(self):
        assert leite_para_kg(1000.0, "arroba") == 1000.0

    def test_litro_minusculo_tambem_converte(self):
        assert leite_para_kg(1000.0, "l") == pytest.approx(1029.0)


class TestImpactoNoBalanco:
    def test_erro_evitado_em_100_mil_litros(self):
        # 100.000 L entregues são 102.900 kg. Contando como 100.000 kg, o
        # "não entregue" ganhava 2.900 kg fantasmas por mês.
        entregue_kg = leite_para_kg(100_000.0, "L")
        assert entregue_kg - 100_000.0 == pytest.approx(2_900.0, abs=1.0)
