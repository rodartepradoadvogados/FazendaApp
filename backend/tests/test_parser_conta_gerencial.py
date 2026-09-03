"""
Teste de regressão do parser de CONTA_GERENCIAL.csv (importação em massa do
Ideagri, ver `POST /upload/conta_gerencial`).

Bug: a coluna "Parcela" do CSV (formato Ideagri "N de M", ex.: "1 de 3") era
completamente ignorada — toda linha nascia com `parcela_num`/`parcela_total`
em None, e o Financeiro mostrava "(null/1)", "(null/2)" etc. no lugar do
número da parcela (ver frontend/app/financeiro/page.tsx, coluna "Nº lanç."
da tabela de Lançamentos).
"""
from __future__ import annotations

from fazenda.parsers.conta_gerencial import _parse_parcela, parse_conta_gerencial

CABECALHO = (
    "Conta gerencial;Descrição;Data venc.;Data pag. / receb.;Data comp.;"
    "Fornecedor / cliente;Nº da nota;Parcela;Valor total da parcela;"
    "Valor parcela aprop. ct. gerencial;Valor aprop. centros de custos;"
    "Valor pago receb.;TIPO;Centro de custo;DATAEMISSAO;\n"
)


def _csv(*linhas: str) -> bytes:
    return (CABECALHO + "\n".join(linhas) + "\n").encode("windows-1252")


class TestParseParcela:
    """Unidade: conversão isolada do texto "N de M" do Ideagri."""

    def test_parcela_unica(self):
        assert _parse_parcela("1 de 1") == (1, 1)

    def test_parcela_do_meio_de_um_parcelamento(self):
        assert _parse_parcela("2 de 3") == (2, 3)

    def test_ultima_parcela(self):
        assert _parse_parcela("12 de 12") == (12, 12)

    def test_vazio_vira_parcela_unica_nunca_none(self):
        # Nunca None — mesmo padrão usado em todo o resto do código
        # (criar_lancamento, compra/venda de animal, RH, comissão...) para
        # "lançamento sem parcelamento".
        assert _parse_parcela("") == (1, 1)
        assert _parse_parcela(None) == (1, 1)

    def test_formato_inesperado_vira_parcela_unica(self):
        assert _parse_parcela("qualquer coisa") == (1, 1)
        assert _parse_parcela("1/3") == (1, 1)


class TestParseContaGerencialPreenchePrcela:
    """Integração: o CSV inteiro, passando pelo parser público."""

    def test_linha_com_parcelamento_preenche_parcela_num_e_total(self):
        conteudo = _csv(
            "3.01.03.01;Ração;25/06/2026;25/06/2026;25/06/2026;"
            "Agropecuária X;83560;2 de 3;1000,00;1000,00;1000,00;1000,00;2;PL;31/05/2026;"
        )
        contas = parse_conta_gerencial(conteudo)
        assert len(contas) == 1
        assert contas[0].parcela_num == 2
        assert contas[0].parcela_total == 3

    def test_linha_sem_parcelamento_vira_1_de_1_nao_none(self):
        conteudo = _csv(
            "2.01.01.01;Leite indústria;25/06/2026;25/06/2026;25/06/2026;"
            "ITALAC;83560;1 de 1;50609,19;50609,19;50609,19;50609,19;1;PL;31/05/2026;"
        )
        contas = parse_conta_gerencial(conteudo)
        assert contas[0].parcela_num == 1
        assert contas[0].parcela_total == 1
        assert contas[0].parcela_num is not None
        assert contas[0].parcela_total is not None

    def test_coluna_parcela_ausente_ou_vazia_nao_gera_null(self):
        # Regressão direta do bug: antes da correção, qualquer linha (com ou
        # sem a coluna preenchida) saía do parser com os dois campos None.
        conteudo = _csv(
            "3.01.03.01;Diesel;25/06/2026;25/06/2026;25/06/2026;"
            "Posto Y;9999;;800,00;800,00;800,00;800,00;2;PL;31/05/2026;"
        )
        contas = parse_conta_gerencial(conteudo)
        assert contas[0].parcela_num == 1
        assert contas[0].parcela_total == 1

    def test_todas_as_parcelas_de_um_parcelamento_completo(self):
        conteudo = _csv(
            "3.01.03.01;Adubo;10/01/2026;;10/01/2026;Fornecedor Z;1;1 de 3;100,00;100,00;100,00;;2;PL;05/01/2026;",
            "3.01.03.01;Adubo;10/02/2026;;10/01/2026;Fornecedor Z;1;2 de 3;100,00;100,00;100,00;;2;PL;05/01/2026;",
            "3.01.03.01;Adubo;10/03/2026;;10/01/2026;Fornecedor Z;1;3 de 3;100,00;100,00;100,00;;2;PL;05/01/2026;",
        )
        contas = parse_conta_gerencial(conteudo)
        assert [(c.parcela_num, c.parcela_total) for c in contas] == [(1, 3), (2, 3), (3, 3)]
        assert all(c.parcela_num is not None and c.parcela_total is not None for c in contas)
