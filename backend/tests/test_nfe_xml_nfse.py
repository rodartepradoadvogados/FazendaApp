"""
Testes do motor de leitura de nota fiscal (backend/fazenda/rules/nfe_xml.py):
- NF-e de mercadoria com desconto e acréscimo (campos antes ignorados).
- NFS-e de serviço (schema municipal, tags fora do caminho fixo de NF-e).
- XML inválido/vazio dando erro claro.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Fornecedor
from fazenda.rules.nfe_xml import parse_nfe_xml

NFE_COM_DESCONTO_E_ACRESCIMO = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe321" versao="4.00">
      <ide>
        <mod>55</mod>
        <nNF>5555</nNF>
        <dhEmi>2026-03-20T08:30:00-03:00</dhEmi>
      </ide>
      <emit><xNome>Insumos Agropecuários LTDA</xNome></emit>
      <det nItem="1">
        <prod>
          <xProd>Adubo NPK 20-05-20</xProd>
          <qCom>50</qCom>
          <vUnCom>60.00</vUnCom>
          <vProd>3000.00</vProd>
        </prod>
      </det>
      <total>
        <ICMSTot>
          <vNF>2980.00</vNF>
          <vDesc>50.00</vDesc>
          <vOutro>30.00</vOutro>
        </ICMSTot>
      </total>
      <cobr>
        <dup><nDup>001</nDup><dVenc>2026-04-20</dVenc><vDup>1490.00</vDup></dup>
        <dup><nDup>002</nDup><dVenc>2026-05-20</dVenc><vDup>1490.00</vDup></dup>
      </cobr>
    </infNFe>
  </NFe>
</nfeProc>
"""

# NFS-e "estilo ABRASF" — o padrão mais comum entre prefeituras, mas com
# nomes/estrutura que variam de município para município na prática.
NFSE_EXEMPLO = """<?xml version="1.0" encoding="UTF-8"?>
<CompNfse xmlns="http://www.abrasf.org.br/nfse.xsd">
  <Nfse>
    <InfNfse Id="nfse-987">
      <Numero>987</Numero>
      <DataEmissao>2026-05-10T14:00:00</DataEmissao>
      <PrestadorServico>
        <IdentificacaoPrestador>
          <Cnpj>12345678000199</Cnpj>
        </IdentificacaoPrestador>
        <RazaoSocial>Serviços Veterinários São José LTDA</RazaoSocial>
      </PrestadorServico>
      <TomadorServico>
        <RazaoSocial>Fazenda Estreito Ponte de Pedra</RazaoSocial>
      </TomadorServico>
      <DeclaracaoPrestacaoServico>
        <InfDeclaracaoPrestacaoServico>
          <Servico>
            <Valores>
              <ValorServicos>1200.00</ValorServicos>
              <ValorDeducoes>50.00</ValorDeducoes>
            </Valores>
            <Discriminacao>Serviço de consultoria veterinária - visita mensal ao rebanho</Discriminacao>
          </Servico>
        </InfDeclaracaoPrestacaoServico>
      </DeclaracaoPrestacaoServico>
      <ValoresNfse>
        <ValorLiquidoNfse>1150.00</ValorLiquidoNfse>
      </ValoresNfse>
    </InfNfse>
  </Nfse>
</CompNfse>
"""


class TestParseNfeMercadoriaComDescontoEAcrescimo:
    def test_extrai_desconto_e_acrescimo(self):
        r = parse_nfe_xml(NFE_COM_DESCONTO_E_ACRESCIMO)
        assert r["valor_total"] == 2980.00
        assert r["desconto"] == 50.00
        assert r["acrescimo"] == 30.00

    def test_extrai_tipo_documento(self):
        r = parse_nfe_xml(NFE_COM_DESCONTO_E_ACRESCIMO)
        assert r["tipo_documento"] == "NF-e"

    def test_preserva_numero_da_duplicata_em_cada_parcela(self):
        r = parse_nfe_xml(NFE_COM_DESCONTO_E_ACRESCIMO)
        assert len(r["parcelas"]) == 2
        assert r["parcelas"][0]["numero"] == "001"
        assert r["parcelas"][1]["numero"] == "002"

    def test_nao_quebra_nota_sem_desconto_nem_acrescimo(self):
        # Retrocompatibilidade: XML antigo sem vDesc/vOutro continua
        # funcionando, só que com desconto/acrescimo = None.
        xml_sem_extra = """<?xml version="1.0"?>
        <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
          <NFe><infNFe Id="x">
            <ide><nNF>1</nNF><dhEmi>2026-01-01T00:00:00-03:00</dhEmi></ide>
            <emit><xNome>Fornecedor Y</xNome></emit>
            <total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>
          </infNFe></NFe>
        </nfeProc>"""
        r = parse_nfe_xml(xml_sem_extra)
        assert r["valor_total"] == 100.00
        assert r["desconto"] is None
        assert r["acrescimo"] is None


class TestParseNfse:
    def test_reconhece_nfse_e_nao_lanca_erro(self):
        r = parse_nfe_xml(NFSE_EXEMPLO)
        assert r["tipo_documento"] == "NFS-e"

    def test_extrai_numero_e_data_emissao(self):
        r = parse_nfe_xml(NFSE_EXEMPLO)
        assert r["numero_documento"] == "987"
        assert r["data_emissao"] == "2026-05-10"

    def test_extrai_prestador_como_fornecedor_nao_o_tomador(self):
        r = parse_nfe_xml(NFSE_EXEMPLO)
        assert r["fornecedor_cliente"] == "Serviços Veterinários São José LTDA"

    def test_extrai_valores_de_servico_deducao_e_liquido(self):
        r = parse_nfe_xml(NFSE_EXEMPLO)
        assert r["valor_servicos"] == 1200.00
        assert r["desconto"] == 50.00
        assert r["valor_liquido"] == 1150.00
        # valor_total usa o líquido quando disponível (é o que efetivamente
        # deve ser lançado/pago).
        assert r["valor_total"] == 1150.00

    def test_discriminacao_vira_descricao_do_item(self):
        r = parse_nfe_xml(NFSE_EXEMPLO)
        assert len(r["itens"]) == 1
        assert "consultoria veterinária" in r["itens"][0]["produto"]

    def test_nfse_sem_alguns_campos_no_devolve_none_sem_explodir(self):
        # NFS-e minimalista, faltando prestador/valores — cada campo ausente
        # deve virar None, sem lançar exceção.
        nfse_minima = """<?xml version="1.0"?>
        <Nfse>
          <InfNfse>
            <Numero>1</Numero>
          </InfNfse>
        </Nfse>"""
        r = parse_nfe_xml(nfse_minima)
        assert r["tipo_documento"] == "NFS-e"
        assert r["numero_documento"] == "1"
        assert r["fornecedor_cliente"] is None
        assert r["valor_total"] is None
        assert r["itens"] == []
        assert r["parcelas"] == []


class TestErrosDeEntrada:
    def test_xml_vazio_da_erro_claro(self):
        with pytest.raises(ValueError, match="vazio"):
            parse_nfe_xml("")

    def test_xml_so_espacos_da_erro_claro(self):
        with pytest.raises(ValueError, match="vazio"):
            parse_nfe_xml("   \n  ")

    def test_xml_malformado_da_erro_claro(self):
        with pytest.raises(ValueError, match="inválido"):
            parse_nfe_xml("<infNFe><ide>oops</ide")  # tag não fechada

    def test_xml_valido_mas_nao_e_nota_fiscal_da_erro_claro(self):
        with pytest.raises(ValueError, match="NF-e"):
            parse_nfe_xml("<mensagem><texto>oi</texto></mensagem>")


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestSugestoesCadastroNoImportarXml:
    """/financeiro/importar-xml devolve, junto dos campos extraídos, as
    sugestões de casamento com o cadastro — ver fazenda.rules.sugestao_documento."""

    def test_fornecedor_parecido_aparece_em_sugestoes_cadastro(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Fornecedor(nome="Agropecuária São José", tipo="fornecedor"))
            s.commit()
        xml = NFE_COM_DESCONTO_E_ACRESCIMO.replace(
            "Insumos Agropecuários LTDA", "Agropecuaria Sao Jose Norte",
        )
        r = c.post("/financeiro/importar-xml", json={"xml": xml})
        assert r.status_code == 200
        sug = r.json()["sugestoes_cadastro"]
        assert sug["fornecedor"]["candidato"] == "Agropecuária São José"
        assert sug["fornecedor"]["confianca"] == "provavel"

    def test_sem_cadastro_parecido_sugestoes_ficam_vazias(self, client):
        c, engine = client
        r = c.post("/financeiro/importar-xml", json={"xml": NFE_COM_DESCONTO_E_ACRESCIMO})
        assert r.status_code == 200
        assert r.json()["sugestoes_cadastro"] == {"fornecedor": None, "itens": []}
