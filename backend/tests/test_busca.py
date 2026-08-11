"""
Testes de fazenda.rules.busca — o normalizador único de texto para busca
(par exato de frontend/lib/busca.test.ts, mesmos casos dos dois lados).
"""
from __future__ import annotations

from fazenda.rules.busca import casa_busca, normalizar_busca


class TestNormalizarBusca:
    def test_ignora_maiuscula_minuscula(self):
        assert normalizar_busca("PROTEINA") == normalizar_busca("proteina")
        assert normalizar_busca("Ração") == normalizar_busca("ração")

    def test_ignora_acento(self):
        assert normalizar_busca("racao") == normalizar_busca("Ração")
        assert normalizar_busca("PROTEINA") == normalizar_busca("Proteína")

    def test_ignora_cedilha(self):
        assert normalizar_busca("coracao") == normalizar_busca("coração")

    def test_ignora_hifen(self):
        assert normalizar_busca("sal-mineral") == normalizar_busca("salmineral")

    def test_ignora_underscore(self):
        assert normalizar_busca("sal_mineral") == normalizar_busca("salmineral")

    def test_ignora_espaco(self):
        assert normalizar_busca("sal mineral") == normalizar_busca("salmineral")

    def test_hifen_underscore_espaco_sao_equivalentes_entre_si(self):
        variantes = ["salmineral", "sal-mineral", "sal_mineral", "sal mineral", "SAL-MINERAL", "Sal_Mineral"]
        assert len({normalizar_busca(v) for v in variantes}) == 1

    def test_nao_altera_o_texto_original(self):
        original = "Ração 20% Proteína"
        normalizar_busca(original)
        assert original == "Ração 20% Proteína"

    def test_none_e_vazio_viram_string_vazia(self):
        assert normalizar_busca(None) == ""
        assert normalizar_busca("") == ""


class TestCasaBusca:
    def test_combinacao_acento_maiuscula_separador(self):
        assert casa_busca("salmineral20", "Sal-Mineral 20%") is True
        assert casa_busca("RACAO DE PROTEINA", "Ração de Proteína") is True
        assert casa_busca("racaodeproteina", "Ração de Proteína") is True

    def test_termo_vazio_sempre_casa(self):
        assert casa_busca("", "qualquer coisa") is True
        assert casa_busca("   ", "qualquer coisa") is True
        assert casa_busca(None, "qualquer coisa") is True

    def test_valores_vazios_ou_nulos_nao_casam_com_termo_real(self):
        assert casa_busca("racao", "") is False
        assert casa_busca("racao", None) is False

    def test_termo_que_nao_aparece_nao_casa(self):
        assert casa_busca("silagem", "Ração de Proteína") is False

    def test_casa_em_qualquer_um_dos_valores_passados(self):
        # Mesmo padrão de uso do `_contem` em rules/exclusao_tipos/_base.py:
        # vários campos candidatos, casa se achar em QUALQUER um deles.
        assert casa_busca("mineral", "Concentrado", "Sal Mineral", "Observação") is True
        assert casa_busca("inexistente", "Concentrado", "Sal Mineral", "Observação") is False

    def test_exemplos_reais_do_dominio(self):
        # Produto.
        assert casa_busca("concentrado proteico", "Ração Concentrado Proteico") is True
        # Serviço.
        assert casa_busca("inseminacao artificial", "Inseminação Artificial") is True
        # Fornecedor.
        assert casa_busca("joao nutricao", "João Nutrição Animal Ltda") is True
