"""
Testes do motor de casamento (fuzzy match) com os cadastros —
backend/fazenda/rules/casamento_cadastro.py. Cobre as 3 faixas de confiança
("exato", "provavel", "incerto"), incluindo casos reais de razão social e
produto com grafia diferente.
"""
from __future__ import annotations

from fazenda.rules.casamento_cadastro import (
    EXATO,
    INCERTO,
    PROVAVEL,
    melhor_candidato,
    normalizar,
)


class TestNormalizar:
    def test_minusculas_sem_acento_sem_pontuacao(self):
        assert normalizar("Agropecuária São José, LTDA.") == "agropecuaria sao jose"

    def test_colapsa_espacos(self):
        assert normalizar("Ração   Concentrada") == "racao concentrada"

    def test_texto_vazio_ou_none(self):
        assert normalizar("") == ""
        assert normalizar(None) == ""

    def test_remove_apenas_palavras_ruido_conhecidas(self):
        # "sal" não é palavra-ruído — só sufixos societários/ramo genérico.
        assert normalizar("Sal Mineral LTDA") == "sal mineral"


class TestFaixaExata:
    def test_fornecedor_razao_social_com_e_sem_sufixo_societario(self):
        resultado = melhor_candidato(
            "AGROPECUARIA SAO JOSE LTDA",
            ["Agropecuária São José", "Cooperativa Central", "Distribuidora Nordeste"],
        )
        assert resultado["candidato"] == "Agropecuária São José"
        assert resultado["confianca"] == EXATO
        assert resultado["score"] == 1.0

    def test_string_identica(self):
        resultado = melhor_candidato("Ração Concentrada 25kg", ["Ração Concentrada 25kg"])
        assert resultado["confianca"] == EXATO

    def test_diferenca_so_de_caixa_e_acento(self):
        resultado = melhor_candidato("racao concentrada", ["Ração Concentrada"])
        assert resultado["confianca"] == EXATO


class TestFaixaProvavel:
    def test_produto_com_grafia_diferente_sufixo_de_embalagem(self):
        # A nota traz o peso no nome, o cadastro não — grafia parecida mas
        # não idêntica após normalizar; deve sugerir com confirmação.
        resultado = melhor_candidato(
            "Ração Concentrada 25kg",
            ["Ração Concentrada", "Sal Mineral", "Adubo NPK"],
        )
        assert resultado["candidato"] == "Ração Concentrada"
        assert resultado["confianca"] == PROVAVEL
        assert 0.80 <= resultado["score"] < 1.0

    def test_razao_social_abreviada_de_forma_diferente(self):
        resultado = melhor_candidato(
            "Coop Agropecuaria Vale Verde",
            ["Cooperativa Agropecuária Vale Verde Ltda"],
        )
        assert resultado["confianca"] in (PROVAVEL, EXATO)  # nunca incerto neste caso
        assert resultado["candidato"] == "Cooperativa Agropecuária Vale Verde Ltda"


class TestFaixaIncerta:
    def test_produtos_completamente_diferentes(self):
        resultado = melhor_candidato("Ração Concentrada", ["Sal Mineral", "Adubo NPK", "Vacina Aftosa"])
        assert resultado["confianca"] == INCERTO
        assert resultado["score"] < 0.80

    def test_fornecedor_sem_nenhuma_semelhanca(self):
        resultado = melhor_candidato(
            "João da Silva Comércio de Peças",
            ["Cooperativa Central de Laticínios", "Distribuidora Nordeste de Insumos"],
        )
        assert resultado["confianca"] == INCERTO

    def test_lista_de_candidatos_vazia(self):
        resultado = melhor_candidato("Qualquer Coisa", [])
        assert resultado == {"candidato": None, "score": 0.0, "confianca": INCERTO}

    def test_texto_vazio_ou_none(self):
        assert melhor_candidato("", ["Algo"])["confianca"] == INCERTO
        assert melhor_candidato(None, ["Algo"])["confianca"] == INCERTO
        assert melhor_candidato("", ["Algo"])["candidato"] is None


class TestEscolheOMelhorEntreVariosCandidatos:
    def test_escolhe_o_de_maior_score_nao_o_primeiro(self):
        resultado = melhor_candidato(
            "Ração Concentrada 25kg",
            ["Adubo NPK", "Ração Concentrada", "Sal Mineral"],
        )
        assert resultado["candidato"] == "Ração Concentrada"

    def test_serve_para_servico_tambem(self):
        # A função é genérica — mesmo comportamento para nome de serviço.
        resultado = melhor_candidato(
            "Consultoria Veterinária Mensal",
            ["Consultoria Veterinária", "Exame de Brucelose", "Vacinação"],
        )
        assert resultado["candidato"] == "Consultoria Veterinária"
        assert resultado["confianca"] in (PROVAVEL, EXATO)
