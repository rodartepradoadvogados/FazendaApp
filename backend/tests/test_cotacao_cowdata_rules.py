"""
Regras puras do catálogo/cotação CowData — ver fazenda/rules/cotacao_cowdata.py.
"""
from __future__ import annotations

from fazenda.rules.cotacao_cowdata import (
    montar_mensagem_cotacao_cowdata, rotulo_item_cotacao_cowdata, sugestoes_duplicata,
)


class TestSugestoesDuplicata:
    def test_nome_identico_normalizado_sugere(self):
        r = sugestoes_duplicata("Silagem de Milho", [(1, "silagem de milho")])
        assert len(r) == 1 and r[0]["id"] == 1

    def test_nome_bem_diferente_nao_sugere(self):
        r = sugestoes_duplicata("Vacina Aftosa", [(1, "Farelo de soja")])
        assert r == []

    def test_nome_curto_ou_vazio_nao_quebra(self):
        assert sugestoes_duplicata("", [(1, "algo")]) == []

    def test_ordena_do_mais_parecido(self):
        r = sugestoes_duplicata("Silagem de milho picada", [(1, "Silagem de milho"), (2, "Silagem")])
        assert [x["id"] for x in r][0] == 1


class TestRotuloItem:
    def test_modo_produto_usa_nome_do_produto(self):
        assert rotulo_item_cotacao_cowdata("produto", produto_nome="Silagem de milho") == "Silagem de milho"

    def test_modo_classificacao_usa_nome_da_classificacao(self):
        assert rotulo_item_cotacao_cowdata("classificacao", classificacao_nome="Medicamentos") == "Medicamentos"

    def test_modo_finalidade_usa_nome_da_finalidade(self):
        assert rotulo_item_cotacao_cowdata("finalidade", finalidade_nome="Energético") == "Energético"


class TestMontarMensagem:
    def test_nunca_expoe_nome_do_campo_interno(self):
        msg = montar_mensagem_cotacao_cowdata(["Medicamentos"])
        assert msg == "Cotação de: Medicamentos"
        assert "classificacao" not in msg.lower() and "finalidade" not in msg.lower()

    def test_com_descricao_livre_anexa_ao_final(self):
        msg = montar_mensagem_cotacao_cowdata(["Energético"], "milho moído, farelo de soja")
        assert msg == "Cotação de: Energético — milho moído, farelo de soja"
