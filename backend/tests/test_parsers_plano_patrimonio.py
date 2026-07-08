"""
Testes dos parsers de Plano de Contas Gerenciais e Patrimônio.
"""
from __future__ import annotations

from datetime import date

from fazenda.parsers.patrimonio import parse_patrimonio
from fazenda.parsers.plano_conta_gerencial import parse_plano_conta_gerencial

PLANO_CSV = (
    "N° ct. ger.;Nome ct. ger.;Ativa;Part. ativ.;Fluxo;Tipo F/V;\n"
    "2;Receita;Não;Não;Não;;\n"
    "2.01.01.01;Leite indústria;Sim;Sim;Sim;;\n"
    "3.01.01.01;Concentrado protéico;Sim;Sim;Sim;Variável;\n"
    "Não informada;Não informada;Não;Não;Não;;\n"
).encode("windows-1252")

PATRIMONIO_CSV = (
    "Tipo patr.;Nome Patr.;N° patr.;Ativ. cul.;Placa;Dt. imob.;Mét. depr.;Vd. útil;Vlr. res.;Quant.;Uni.;Vlr. tot.;Dt. baixa pat.;\n"
    "Implemento;ENXADA ROTATIVA ERG 2000 - GELGÁS;7;;;01/05/2026;Linear;7 Anos;6875;1;un;27500;;\n"
    "Terra;Fazenda;1;;;01/01/2025;;;;1;ha;334215,56;;\n"
).encode("windows-1252")


class TestParsePlanoContaGerencial:
    def test_extrai_contas_com_hierarquia(self):
        contas = parse_plano_conta_gerencial(PLANO_CSV)
        assert len(contas) == 4
        c = contas[1]
        assert c.codigo == "2.01.01.01"
        assert c.nome == "Leite indústria"
        assert c.ativa is True
        assert c.participa_atividade is True
        assert c.fluxo is True

    def test_conta_inativa(self):
        contas = parse_plano_conta_gerencial(PLANO_CSV)
        raiz = contas[0]
        assert raiz.codigo == "2"
        assert raiz.ativa is False

    def test_tipo_fixo_variavel(self):
        contas = parse_plano_conta_gerencial(PLANO_CSV)
        despesa = next(c for c in contas if c.codigo == "3.01.01.01")
        assert despesa.tipo_fixo_variavel == "Variável"


class TestParsePatrimonio:
    def test_extrai_itens(self):
        itens = parse_patrimonio(PATRIMONIO_CSV)
        assert len(itens) == 2
        implemento = itens[0]
        assert implemento.nome == "ENXADA ROTATIVA ERG 2000 - GELGÁS"
        assert implemento.tipo == "Implemento"
        assert implemento.numero == "7"
        assert implemento.data_imobilizacao == date(2026, 5, 1)
        assert implemento.metodo_depreciacao == "Linear"
        assert implemento.vida_util == "7 Anos"
        assert implemento.valor_residual == 6875.0
        assert implemento.valor_total == 27500.0

    def test_valor_com_separador_de_milhar(self):
        itens = parse_patrimonio(PATRIMONIO_CSV)
        terra = next(i for i in itens if i.nome == "Fazenda")
        assert terra.valor_total == 334215.56
        assert terra.unidade == "ha"
