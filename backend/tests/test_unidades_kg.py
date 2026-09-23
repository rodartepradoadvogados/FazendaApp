"""
Conversão de unidade para quilos (`rules/unidades.py`).

O teste que mais importa aqui é o do `None`. A tentação de devolver 0.0 para
uma unidade sem massa é grande — o código fica mais simples e nada estoura. Mas
um zero entra silenciosamente na soma do fornecido, o denominador do percentual
de sobra fica MENOR do que a realidade, e a sobra parece proporcionalmente
MAIOR do que é. O alerta então manda REDUZIR o trato de um lote que na verdade
está comendo tudo — que é o erro mais caro que este subsistema pode cometer.

Por isso os casos sem conversão estão travados aqui como `is None`, e não como
"falsy": `0.0` também é falsy, e passaria despercebido numa asserção frouxa.
"""
from __future__ import annotations

import pytest

from fazenda.rules.unidades import UNIDADES_SEM_MASSA, converte_para_kg, de_kg_para_unidade, kg_equivalente


class TestConversaoParaQuilos:
    @pytest.mark.parametrize(
        "quantidade,unidade,esperado",
        [
            (10, "kg", 10.0),
            (2.5, "kg", 2.5),
            (500, "g", 0.5),
            (1, "saca 30kg", 30.0),
            (2, "saca 60kg", 120.0),
        ],
    )
    def test_converte_o_que_e_massa(self, quantidade, unidade, esperado):
        assert kg_equivalente(quantidade, unidade) == pytest.approx(esperado)

    def test_saca_converte_e_esse_e_o_ponto(self):
        """A saca é o motivo de este módulo existir: o fator está escrito no
        nome da unidade, e mesmo assim ela ficava fora de todo total em quilos
        do sistema (ver `vagao_kg_dia`, que soma só kg/g)."""
        assert kg_equivalente(1, "saca 30kg") == 30.0
        assert kg_equivalente(1, "saca 60kg") == 60.0

    @pytest.mark.parametrize("unidade", sorted(UNIDADES_SEM_MASSA))
    def test_unidade_sem_massa_devolve_none_e_nao_zero(self, unidade):
        r = kg_equivalente(10, unidade)
        assert r is None, f"{unidade} devolveu {r!r} — zero soma em silêncio e vira alerta errado"

    def test_unidade_desconhecida_tambem_devolve_none(self):
        """Texto que ninguém previu tem a mesma resposta honesta: não sei."""
        assert kg_equivalente(10, "carrinho de mão") is None
        assert kg_equivalente(10, "") is None
        assert kg_equivalente(10, None) is None

    def test_quantidade_nula_devolve_none(self):
        assert kg_equivalente(None, "kg") is None

    def test_ignora_caixa_e_espacos(self):
        assert kg_equivalente(1, "  KG ") == 1.0
        assert kg_equivalente(1, "Saca 30Kg") == 30.0

    def test_zero_quilos_e_resposta_valida_diferente_de_none(self):
        """Lançar 0 kg é lançamento legítimo (o vagão não passou). Não pode ser
        confundido com 'unidade não converte'."""
        assert kg_equivalente(0, "kg") == 0.0
        assert kg_equivalente(0, "kg") is not None


class TestConverteParaKg:
    """A tela precisa marcar o item ANTES de haver quantidade lançada."""

    def test_diz_o_que_converte(self):
        assert converte_para_kg("kg") is True
        assert converte_para_kg("saca 60kg") is True

    def test_diz_o_que_nao_converte(self):
        assert converte_para_kg("dose") is False
        assert converte_para_kg("L") is False
        assert converte_para_kg(None) is False

    def test_concorda_com_kg_equivalente(self):
        """As duas funções não podem divergir — seria pior que ter só uma."""
        for u in ["kg", "g", "saca 30kg", "saca 60kg", *UNIDADES_SEM_MASSA, "inventada"]:
            assert converte_para_kg(u) == (kg_equivalente(1, u) is not None), u


class TestDeKgParaUnidade:
    """Inverso de `kg_equivalente` — usado pelo lançamento "kg do vagão"
    (Lançamentos > Alimentação) para converter a fatia em quilos de volta pra
    unidade do item ANTES de gravar, porque `pode_dar_baixa_direta` só aceita
    igualdade exata de unidade com o Estoque."""

    @pytest.mark.parametrize(
        "kg,unidade,esperado",
        [
            (10, "kg", 10.0),
            (2.5, "kg", 2.5),
            (0.5, "g", 500.0),
            (30, "saca 30kg", 1.0),
            (120, "saca 60kg", 2.0),
        ],
    )
    def test_inverso_de_kg_equivalente(self, kg, unidade, esperado):
        assert de_kg_para_unidade(kg, unidade) == pytest.approx(esperado)

    def test_ida_e_volta_bate_pra_qualquer_unidade_de_massa(self):
        for unidade in ("kg", "g", "saca 30kg", "saca 60kg"):
            for quantidade in (0, 1, 3.5, 100):
                kg = kg_equivalente(quantidade, unidade)
                assert de_kg_para_unidade(kg, unidade) == pytest.approx(quantidade)

    @pytest.mark.parametrize("unidade", sorted(UNIDADES_SEM_MASSA))
    def test_unidade_sem_massa_devolve_none(self, unidade):
        assert de_kg_para_unidade(10, unidade) is None

    def test_kg_nulo_devolve_none(self):
        assert de_kg_para_unidade(None, "kg") is None
