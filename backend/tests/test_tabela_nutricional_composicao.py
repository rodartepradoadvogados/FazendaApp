"""
Compor AlimentoNutricional a partir da Tabela Nutricional (01/09/2026) —
pedido do usuário: usar a composição já digitada por produto (texto livre,
unidades mistas) em vez do template genérico ao importar do cadastro na
Formulação de Dietas. Ver docstring de
fazenda.rules.tabela_nutricional.compor_alimento_nutricional_de_tabela.
"""
from __future__ import annotations

from fazenda.rules.tabela_nutricional import ALIMENTOS, LINHAS, compor_alimento_nutricional_de_tabela, parse_valor


def _coluna(nome_alimento: str) -> dict[str, str]:
    idx = ALIMENTOS.index(nome_alimento)
    return {linha[0]: linha[idx + 1] for linha in LINHAS}


class TestParseValor:
    def test_valor_com_unidade_mg(self):
        assert parse_valor("5.500,00 mg") == (5500.0, "mg")

    def test_valor_percentual_com_base(self):
        assert parse_valor("6,71% MS") == (6.71, "% MS")

    def test_valor_inteiro_sem_decimal(self):
        assert parse_valor("100 g (Máx)") == (100.0, "g (Máx)")

    def test_nao_informado_da_none(self):
        assert parse_valor("Não informado") is None

    def test_vazio_da_none(self):
        assert parse_valor("") is None
        assert parse_valor(None) is None  # type: ignore[arg-type]


class TestComporDeVolumosoJaEmPctMS:
    """Silagem: valores já vêm como "% MS" — usa direto, sem conversão de unidade."""

    def test_campos_percentuais_batem_direto(self):
        convertidos, nao_convertidos = compor_alimento_nutricional_de_tabela(_coluna("SILAGEM DE MILHO (60d)"))
        assert convertidos["ms_pct"] == 33.24
        assert convertidos["pb_pct"] == 6.71
        assert convertidos["fdn_pct"] == 44.50
        assert convertidos["fda_pct"] == 27.02
        assert convertidos["cinzas_pct"] == 4.50
        assert convertidos["amido_pct"] == 28.63
        assert convertidos["lignina_pct"] == 5.14
        assert convertidos["ca_pct"] == 0.17
        assert convertidos["p_pct"] == 0.19
        assert convertidos["mg_pct"] == 0.12
        assert convertidos["s_pct"] == 0.07
        assert convertidos["k_pct"] == 0.98
        assert convertidos["pida_pct"] == 0.32
        assert convertidos["pidn_pct"] == 0.90
        # "Proteína Solúvel" é "% PB" (base diferente, sem campo tipado) e
        # "Sódio (Mín)" está vazio nesta coluna — os dois não geram erro nem
        # aparecem como convertidos.
        assert "na_pct" not in convertidos
        assert "Proteína Solúvel" in nao_convertidos


class TestComporDeConcentradoComercial:
    """Teck Milk 24%: garantias de rótulo em g/mg por kg de PRODUTO — precisa
    derivar a MS da Umidade e reexpressar tudo em % da MS."""

    def test_ms_derivada_da_umidade_maxima(self):
        convertidos, _ = compor_alimento_nutricional_de_tabela(_coluna("TECK MILK 24%"))
        # Umidade (Máx) = 125,00 g/kg = 12,5% -> MS >= 87,5%
        assert convertidos["ms_pct"] == 87.5

    def test_proteina_bruta_reexpressa_em_pct_ms(self):
        convertidos, _ = compor_alimento_nutricional_de_tabela(_coluna("TECK MILK 24%"))
        # 240 g/kg = 24% como oferecido; /0,875 (MS) = 27,43% da MS
        assert convertidos["pb_pct"] == 27.43

    def test_calcio_usa_a_variante_minimo_e_ignora_o_maximo(self):
        convertidos, _ = compor_alimento_nutricional_de_tabela(_coluna("TECK MILK 24%"))
        # 5.500 mg/kg = 0,55% como oferecido; /0,875 = 0,63% da MS
        assert convertidos["ca_pct"] == 0.63

    def test_nutrientes_sem_campo_tipado_viram_nao_convertidos(self):
        _, nao_convertidos = compor_alimento_nutricional_de_tabela(_coluna("TECK MILK 24%"))
        assert nao_convertidos["Vitamina A (Mín)"] == "13.300,00 UI"
        assert nao_convertidos["Cobalto (Mín)"] == "0,80 mg"
        assert nao_convertidos["Saccharomyces cerevisiae"] == "400.000,00 ufc/g"

    def test_nao_informado_nao_polui_a_lista_de_nao_convertidos(self):
        # BEZERRO 1 tem "Ferro (Mín)": "Não informado" — não é um dado de
        # verdade, não deve aparecer como pendência de conversão.
        _, nao_convertidos = compor_alimento_nutricional_de_tabela(_coluna("BEZERRO 1"))
        assert "Ferro (Mín)" not in nao_convertidos

    def test_usa_maximo_quando_minimo_esta_ausente_na_coluna(self):
        # NNP Eq. Prot. (Máx) não tem campo tipado (fica em não convertidos);
        # já Cálcio testa o caminho normal (Mín presente). Aqui cobrimos o
        # caminho fallback com um caso sintético: só "(Máx)" na coluna.
        convertidos, _ = compor_alimento_nutricional_de_tabela({
            "Matéria Seca (MS)": "90,00%",
            "Fósforo (Máx)": "10,00 g (Máx)",
        })
        assert convertidos["p_pct"] == round(1.0 / 0.9, 2)  # 10g/kg=1% as-fed / 0,90 MS


class TestComporSemMsConhecida:
    """Sem "Matéria Seca" nem "Umidade" na coluna: usa a garantia como
    aproximação direta de % da MS (documentado, não é erro)."""

    def test_usa_valor_como_fed_quando_ms_desconhecida(self):
        convertidos, _ = compor_alimento_nutricional_de_tabela({"Proteína Bruta": "200,00 g (Mín)"})
        assert "ms_pct" not in convertidos
        assert convertidos["pb_pct"] == 20.0  # 200g/kg = 20%, sem correção de MS
