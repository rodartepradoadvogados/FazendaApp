"""
Testes do módulo financeiro: leitura de XML de NF-e e numeração de lançamentos.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.models import ContaGerencial
from fazenda.rules.nfe_xml import parse_nfe_xml

NFE_SIMPLES = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe123" versao="4.00">
      <ide><nNF>4521</nNF><dhEmi>2026-06-15T10:00:00-03:00</dhEmi></ide>
      <emit><xNome>Cooperativa Agro LTDA</xNome></emit>
      <det nItem="1">
        <prod>
          <xProd>Ração concentrada 25kg</xProd>
          <qCom>40.0000</qCom>
          <vUnCom>85.5000</vUnCom>
          <vProd>3420.00</vProd>
        </prod>
      </det>
      <total><ICMSTot><vNF>3420.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
</nfeProc>
"""

NFE_PARCELADA = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe456" versao="4.00">
      <ide><nNF>9001</nNF><dhEmi>2026-01-10T09:00:00-03:00</dhEmi></ide>
      <emit><xNome>Fornecedor Insumos S.A.</xNome></emit>
      <det nItem="1"><prod><xProd>Sal mineral</xProd><qCom>100</qCom><vUnCom>12.0</vUnCom><vProd>1200.00</vProd></prod></det>
      <total><ICMSTot><vNF>1200.00</vNF></ICMSTot></total>
      <cobr>
        <dup><nDup>001</nDup><dVenc>2026-02-10</dVenc><vDup>600.00</vDup></dup>
        <dup><nDup>002</nDup><dVenc>2026-03-10</dVenc><vDup>600.00</vDup></dup>
      </cobr>
    </infNFe>
  </NFe>
</nfeProc>
"""


class TestParseNfeXml:
    def test_extrai_campos_basicos(self):
        r = parse_nfe_xml(NFE_SIMPLES)
        assert r["numero_documento"] == "4521"
        assert r["data_emissao"] == "2026-06-15"
        assert r["fornecedor_cliente"] == "Cooperativa Agro LTDA"
        assert r["valor_total"] == 3420.00
        assert r["descricao"] == "Ração concentrada 25kg"
        assert r["quantidade"] == 40.0
        assert r["valor_unitario"] == 85.5
        assert r["parcelas"] == []

    def test_extrai_parcelas_das_duplicatas(self):
        r = parse_nfe_xml(NFE_PARCELADA)
        assert r["valor_total"] == 1200.00
        assert len(r["parcelas"]) == 2
        assert r["parcelas"][0] == {"numero": "001", "data_vencimento": "2026-02-10", "valor": 600.0}
        assert r["parcelas"][1] == {"numero": "002", "data_vencimento": "2026-03-10", "valor": 600.0}

    def test_xml_invalido_lanca_erro(self):
        with pytest.raises(Exception):
            parse_nfe_xml("<naoehnfe><foo>bar</foo></naoehnfe>")

    def test_doctype_e_removido_antes_do_parse(self):
        # Garante que um DOCTYPE colado junto ao XML não quebra o parser
        # (mitigação simples contra expansão de entidade externa).
        malicioso = "<!DOCTYPE foo [<!ENTITY x \"y\">]>\n" + NFE_SIMPLES
        r = parse_nfe_xml(malicioso)
        assert r["numero_documento"] == "4521"


class TestNumeroLancamento:
    def _sessao(self) -> Session:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(engine)
        return Session(engine)

    def test_primeiro_numero_do_ano(self):
        with self._sessao() as session:
            assert _proximo_numero_lancamento(session, 2026) == "LC-2026-00001"

    def test_incrementa_a_partir_do_maior_existente(self):
        with self._sessao() as session:
            session.add(ContaGerencial(numero_lancamento="LC-2026-00001", valor_total=10))
            session.add(ContaGerencial(numero_lancamento="LC-2026-00007", valor_total=10))
            session.commit()
            assert _proximo_numero_lancamento(session, 2026) == "LC-2026-00008"

    def test_nao_mistura_anos_diferentes(self):
        with self._sessao() as session:
            session.add(ContaGerencial(numero_lancamento="LC-2025-00099", valor_total=10))
            session.commit()
            assert _proximo_numero_lancamento(session, 2026) == "LC-2026-00001"
