"""
Testes do módulo financeiro: leitura de XML de NF-e e numeração de lançamentos.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.api.routers.financeiro import _proximo_numero_lancamento, seed_parametros_financeiros
from fazenda.models import CentroCusto, ContaCorrente, ContaGerencial, Estoque, LancamentoItem, MovimentoEstoque, PlanoContaGerencial
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

NFE_MULTI_ITEM = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe789" versao="4.00">
      <ide><nNF>7777</nNF><dhEmi>2026-04-01T10:00:00-03:00</dhEmi></ide>
      <emit><xNome>Agropecuária Central</xNome></emit>
      <det nItem="1"><prod><xProd>Ração concentrada 25kg</xProd><qCom>10</qCom><vUnCom>85.5</vUnCom><vProd>855.00</vProd></prod></det>
      <det nItem="2"><prod><xProd>Sal mineral 20kg</xProd><qCom>5</qCom><vUnCom>40.0</vUnCom><vProd>200.00</vProd></prod></det>
      <total><ICMSTot><vNF>1055.00</vNF></ICMSTot></total>
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
        assert len(r["itens"]) == 1
        assert r["itens"][0]["produto"] == "Ração concentrada 25kg"
        assert r["itens"][0]["quantidade"] == 40.0
        assert r["itens"][0]["valor_unitario"] == 85.5
        assert r["itens"][0]["valor_total"] == 3420.0
        assert r["parcelas"] == []

    def test_extrai_parcelas_das_duplicatas(self):
        r = parse_nfe_xml(NFE_PARCELADA)
        assert r["valor_total"] == 1200.00
        assert len(r["parcelas"]) == 2
        assert r["parcelas"][0] == {"numero": "001", "data_vencimento": "2026-02-10", "valor": 600.0}
        assert r["parcelas"][1] == {"numero": "002", "data_vencimento": "2026-03-10", "valor": 600.0}

    def test_extrai_multiplos_produtos(self):
        r = parse_nfe_xml(NFE_MULTI_ITEM)
        assert r["valor_total"] == 1055.00
        assert len(r["itens"]) == 2
        assert r["itens"][0]["produto"] == "Ração concentrada 25kg"
        assert r["itens"][0]["valor_total"] == 855.0
        assert r["itens"][1]["produto"] == "Sal mineral 20kg"
        assert r["itens"][1]["valor_total"] == 200.0

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


class TestLancamentoMultiplosItens:
    def test_cria_lancamento_com_dois_produtos(self, client):
        c, engine = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [
                {"produto": "Ração concentrada", "codigo_conta_gerencial": "3.01.01.01", "quantidade": 10, "valor_unitario": 85.5, "valor_total": 855.0},
                {"produto": "Sal mineral", "codigo_conta_gerencial": "3.01.01.03", "quantidade": 5, "valor_unitario": 40.0, "valor_total": 200.0},
            ],
            "data_emissao": "2026-04-01", "valor_pago": None,
        })
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["valor_bruto"] == 1055.0
        assert corpo["valor_liquido"] == 1055.0

        with Session(engine) as s:
            from sqlmodel import select
            itens = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == corpo["numero_lancamento"])).all()
            assert len(itens) == 2
            assert {i.produto for i in itens} == {"Ração concentrada", "Sal mineral"}
            parcela = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == corpo["numero_lancamento"])).first()
            assert parcela.valor_total == 1055.0
            assert "Ração concentrada" in parcela.descricao and "Sal mineral" in parcela.descricao

    def test_tipo_item_e_persistido_por_linha(self, client):
        c, engine = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [
                {"produto": "Ração concentrada", "tipo_item": "produto", "valor_total": 500.0},
                {"produto": "Frete", "tipo_item": "servico", "valor_total": 150.0},
            ],
        })
        assert r.status_code == 201
        corpo = r.json()
        with Session(engine) as s:
            from sqlmodel import select
            itens = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == corpo["numero_lancamento"])).all()
            por_nome = {i.produto: i.tipo_item for i in itens}
            assert por_nome == {"Ração concentrada": "produto", "Frete": "servico"}

    def test_rejeita_tipo_item_invalido(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "X", "tipo_item": "outro", "valor_total": 100.0}],
        })
        assert r.status_code == 400

    def test_desconto_reduz_o_valor_liquido(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração", "valor_total": 1000.0}],
            "desconto": 50.0,
        })
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["valor_bruto"] == 1000.0
        assert corpo["valor_liquido"] == 950.0

    def test_acrescimo_aumenta_o_valor_liquido(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração", "valor_total": 1000.0}],
            "acrescimo": 30.0,
        })
        assert r.status_code == 201
        assert r.json()["valor_liquido"] == 1030.0

    def test_sem_itens_da_erro(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={"tipo": "despesa", "itens": []})
        assert r.status_code == 400

    def test_desconto_maior_que_bruto_da_erro(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "itens": [{"produto": "X", "valor_total": 100.0}], "desconto": 200.0,
        })
        assert r.status_code == 400

    def test_lancamentos_endpoint_traz_itens_agrupados(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [
                {"produto": "Ração", "valor_total": 500.0},
                {"produto": "Sal mineral", "valor_total": 300.0},
            ],
        })
        numero = r.json()["numero_lancamento"]
        listagem = c.get("/financeiro/lancamentos").json()
        registro = next(l for l in listagem["lancamentos"] if l["numero_lancamento"] == numero)
        assert len(registro["itens"]) == 2


class TestPlanoContas:
    def test_traz_contas_ativas_e_de_grupo(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(PlanoContaGerencial(codigo="2", nome="Receita", ativa=False))
            s.add(PlanoContaGerencial(codigo="2.01", nome="Pecuária", ativa=False))
            s.add(PlanoContaGerencial(codigo="2.01.01.01", nome="Leite indústria", ativa=True))
            s.commit()

        r = c.get("/financeiro/plano-contas")
        assert r.status_code == 200
        por_codigo = {x["codigo"]: x for x in r.json()}
        assert por_codigo["2"]["nivel"] == 1
        assert por_codigo["2.01"]["nivel"] == 2
        assert por_codigo["2.01.01.01"]["nivel"] == 4
        assert por_codigo["2"]["ativa"] is False
        assert por_codigo["2.01.01.01"]["ativa"] is True
        assert all(isinstance(x["id"], int) for x in r.json())  # front usa o id para editar

    def test_opcoes_so_traz_contas_ativas_plano_completo_traz_tudo(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(PlanoContaGerencial(codigo="2.01", nome="Pecuária", ativa=False))
            s.add(PlanoContaGerencial(codigo="2.01.01.01", nome="Leite indústria", ativa=True))
            s.commit()

        codigos_opcoes = {x["codigo"] for x in c.get("/financeiro/opcoes").json()["contas_gerenciais"]}
        codigos_completo = {x["codigo"] for x in c.get("/financeiro/plano-contas").json()}
        assert codigos_opcoes == {"2.01.01.01"}
        assert codigos_completo == {"2.01", "2.01.01.01"}


class TestParametrosFinanceiros:
    def test_seed_cria_duas_contas_correntes(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_parametros_financeiros(s)
        r = c.get("/financeiro/contas-correntes")
        assert r.status_code == 200
        assert len(r.json()) == 2
        assert all(x["banco"] == "Banco do Brasil" for x in r.json())

    def test_seed_e_idempotente(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_parametros_financeiros(s)
            seed_parametros_financeiros(s)
        assert len(c.get("/financeiro/contas-correntes").json()) == 2

    def test_cria_conta_corrente(self, client):
        c, engine = client
        r = c.post("/financeiro/contas-correntes", json={"banco": "Sicredi", "agencia": "0001", "numero_conta": "12345-6"})
        assert r.status_code == 200
        assert r.json()["rotulo"] == "Sicredi · Agência 0001 · Conta corrente 12345-6"

    def test_atualizar_conta_corrente(self, client):
        c, engine = client
        conta_id = c.post("/financeiro/contas-correntes", json={"banco": "Sicredi", "agencia": "0001", "numero_conta": "12345-6"}).json()["id"]
        r = c.put(f"/financeiro/contas-correntes/{conta_id}", json={"banco": "Sicredi", "agencia": "0001", "numero_conta": "12345-6", "ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False

    def test_opcoes_so_traz_contas_correntes_ativas(self, client):
        c, engine = client
        conta_id = c.post("/financeiro/contas-correntes", json={"banco": "Sicredi", "agencia": "0001", "numero_conta": "12345-6"}).json()["id"]
        c.put(f"/financeiro/contas-correntes/{conta_id}", json={"banco": "Sicredi", "agencia": "0001", "numero_conta": "12345-6", "ativo": False})
        assert c.get("/financeiro/opcoes").json()["contas_bancarias"] == []

    def test_cria_centro_custo(self, client):
        c, engine = client
        r = c.post("/financeiro/centros-custo", json={"nome": "Ordenha"})
        assert r.status_code == 200
        assert "Ordenha" in [x["nome"] for x in c.get("/financeiro/centros-custo").json()]
        assert "Ordenha" in c.get("/financeiro/opcoes").json()["centros_custo"]

    def test_nao_permite_centro_custo_duplicado(self, client):
        c, engine = client
        c.post("/financeiro/centros-custo", json={"nome": "Ordenha"})
        r = c.post("/financeiro/centros-custo", json={"nome": "Ordenha"})
        assert r.status_code == 409

    def test_centros_custo_listados_em_ordem_alfabetica(self, client):
        c, engine = client
        for nome in ["Secagem", "Bezerreiro", "Ordenha"]:
            c.post("/financeiro/centros-custo", json={"nome": nome})
        assert [x["nome"] for x in c.get("/financeiro/centros-custo").json()] == ["Bezerreiro", "Ordenha", "Secagem"]

    def test_contas_correntes_listadas_em_ordem_alfabetica_por_banco(self, client):
        c, engine = client
        c.post("/financeiro/contas-correntes", json={"banco": "Sicredi", "agencia": "0001", "numero_conta": "1"})
        c.post("/financeiro/contas-correntes", json={"banco": "Banco do Brasil", "agencia": "0002", "numero_conta": "2"})
        bancos = [x["banco"] for x in c.get("/financeiro/contas-correntes").json()]
        assert bancos == ["Banco do Brasil", "Sicredi"]

    def test_centros_custo_ja_usados_em_lancamentos_continuam_nas_opcoes(self, client):
        # Compatibilidade: valores digitados como texto livre antes do cadastro
        # existir não podem desaparecer do filtro.
        c, engine = client
        with Session(engine) as s:
            s.add(ContaGerencial(numero_lancamento="LC-2026-00001", centro_custo="Pasto Legado"))
            s.commit()
        assert "Pasto Legado" in c.get("/financeiro/opcoes").json()["centros_custo"]

    def test_cria_conta_gerencial(self, client):
        c, engine = client
        r = c.post("/financeiro/plano-contas", json={"codigo": "3.09.09.09", "nome": "Conta teste"})
        assert r.status_code == 200
        codigos = {x["codigo"] for x in c.get("/financeiro/plano-contas").json()}
        assert "3.09.09.09" in codigos

    def test_nao_permite_conta_gerencial_com_codigo_duplicado(self, client):
        c, engine = client
        c.post("/financeiro/plano-contas", json={"codigo": "3.09.09.09", "nome": "Conta teste"})
        r = c.post("/financeiro/plano-contas", json={"codigo": "3.09.09.09", "nome": "Outra"})
        assert r.status_code == 409

    def test_atualizar_conta_gerencial(self, client):
        c, engine = client
        conta_id = c.post("/financeiro/plano-contas", json={"codigo": "3.09.09.09", "nome": "Conta teste"}).json()["id"]
        r = c.put(f"/financeiro/plano-contas/{conta_id}", json={"codigo": "3.09.09.09", "nome": "Conta renomeada", "ativa": False})
        assert r.status_code == 200
        assert r.json()["nome"] == "Conta renomeada"
        assert r.json()["ativa"] is False


class TestBaixaLote:
    def _criar_lancamento(self, c, valor=1000.0, produto="Ração"):
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": produto, "quantidade": 1, "valor_unitario": valor, "valor_total": valor}],
        })
        return r.json()["ids"][0]

    def test_baixa_lote_marca_todos_como_pagos(self, client):
        c, engine = client
        id1 = self._criar_lancamento(c, 500.0)
        id2 = self._criar_lancamento(c, 700.0)

        r = c.put("/financeiro/lancamentos/baixa-lote", json={
            "lancamento_ids": [id1, id2], "data_pagamento": "2026-07-08",
            "conta_bancaria": "Banco X", "forma_pagamento": "pix",
            "numero_documento_pagamento": "COMP-001",
        })
        assert r.status_code == 200
        assert r.json()["baixados"] == 2

        lancs = {l["id"]: l for l in c.get("/financeiro/lancamentos").json()["lancamentos"]}
        assert lancs[id1]["valor_pago"] == 500.0
        assert lancs[id2]["valor_pago"] == 700.0
        assert lancs[id1]["forma_pagamento"] == "pix"
        assert lancs[id1]["numero_documento_pagamento"] == "COMP-001"
        assert lancs[id1]["data_pagamento"] == "2026-07-08"

    def test_baixa_lote_credito_exige_vencimento_do_cartao(self, client):
        c, engine = client
        id1 = self._criar_lancamento(c)
        r = c.put("/financeiro/lancamentos/baixa-lote", json={
            "lancamento_ids": [id1], "data_pagamento": "2026-07-08", "forma_pagamento": "credito",
        })
        assert r.status_code == 400

    def test_baixa_lote_credito_com_vencimento_ok(self, client):
        c, engine = client
        id1 = self._criar_lancamento(c)
        r = c.put("/financeiro/lancamentos/baixa-lote", json={
            "lancamento_ids": [id1], "data_pagamento": "2026-07-08", "forma_pagamento": "credito",
            "data_vencimento_cartao": "2026-08-10",
        })
        assert r.status_code == 200
        lanc = next(l for l in c.get("/financeiro/lancamentos").json()["lancamentos"] if l["id"] == id1)
        assert lanc["data_vencimento_cartao"] == "2026-08-10"

    def test_baixa_lote_sem_ids_da_erro(self, client):
        c, engine = client
        r = c.put("/financeiro/lancamentos/baixa-lote", json={"lancamento_ids": [], "data_pagamento": "2026-07-08"})
        assert r.status_code == 400

    def test_baixa_lote_id_inexistente_reportado_sem_quebrar_os_demais(self, client):
        c, engine = client
        id1 = self._criar_lancamento(c)
        r = c.put("/financeiro/lancamentos/baixa-lote", json={
            "lancamento_ids": [id1, 999999], "data_pagamento": "2026-07-08",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["baixados"] == 1
        assert corpo["nao_encontrados"] == [999999]

    def test_baixa_individual_aceita_forma_pagamento(self, client):
        c, engine = client
        id1 = self._criar_lancamento(c, 300.0)
        r = c.put(f"/financeiro/lancamentos/{id1}/pagar", json={
            "data_pagamento": "2026-07-08", "valor_pago": 300.0, "forma_pagamento": "boleto",
        })
        assert r.status_code == 200
        assert r.json()["forma_pagamento"] == "boleto"

    def test_baixa_individual_credito_sem_vencimento_da_erro(self, client):
        c, engine = client
        id1 = self._criar_lancamento(c, 300.0)
        r = c.put(f"/financeiro/lancamentos/{id1}/pagar", json={
            "data_pagamento": "2026-07-08", "valor_pago": 300.0, "forma_pagamento": "credito",
        })
        assert r.status_code == 400


class TestRmca:
    def _marcar_contas(self, session):
        session.add(PlanoContaGerencial(codigo="2.01.01.01", nome="Leite indústria", ativa=True, rmca_receita_leite=True))
        session.add(PlanoContaGerencial(codigo="3.01.01.01", nome="Ração", ativa=True, rmca_custo_alimentacao=True))
        session.commit()

    def test_sem_configuracao_retorna_configurado_falso(self, client):
        c, engine = client
        r = c.get("/financeiro/rmca", params={"data_inicio": "2026-01-01", "data_fim": "2026-01-31"})
        assert r.status_code == 200
        assert r.json()["configurado"] is False

    def test_versao_gerencial_soma_pelas_contas_marcadas(self, client):
        c, engine = client
        with Session(engine) as s:
            self._marcar_contas(s)

        c.post("/financeiro/lancamentos", json={
            "tipo": "receita",
            "itens": [{"produto": "Leite", "codigo_conta_gerencial": "2.01.01.01", "valor_total": 10000.0}],
            "data_competencia": "2026-01-10",
        })
        c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração concentrada", "codigo_conta_gerencial": "3.01.01.01", "valor_total": 3000.0}],
            "data_competencia": "2026-01-15",
        })
        # Fora do período — não deve entrar na soma.
        c.post("/financeiro/lancamentos", json={
            "tipo": "receita",
            "itens": [{"produto": "Leite", "codigo_conta_gerencial": "2.01.01.01", "valor_total": 99999.0}],
            "data_competencia": "2026-03-01",
        })

        r = c.get("/financeiro/rmca", params={"data_inicio": "2026-01-01", "data_fim": "2026-01-31"})
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["configurado"] is True
        assert corpo["gerencial"]["receita_leite"] == 10000.0
        assert corpo["gerencial"]["custo_alimentacao"] == 3000.0
        assert corpo["gerencial"]["rmca"] == 7000.0

    def test_versao_fisica_usa_consumo_real_x_valor_unitario_do_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            self._marcar_contas(s)
            s.add(Estoque(nome="Ração concentrada", quantidade=1000, unidade="kg", valor_unitario=2.5))
            s.commit()

        c.post("/financeiro/lancamentos", json={
            "tipo": "receita",
            "itens": [{"produto": "Leite", "codigo_conta_gerencial": "2.01.01.01", "valor_total": 10000.0}],
            "data_competencia": "2026-01-10",
        })
        with Session(engine) as s:
            s.add(MovimentoEstoque(
                nome_item="Ração concentrada", movimento="Saída de ajuste", quantidade=400,
                unidade="kg", data_movimento=date(2026, 1, 20),
            ))
            # Movimento manual (não da Alimentação) — não deve entrar no custo físico.
            s.add(MovimentoEstoque(
                nome_item="Ração concentrada", movimento="Aplicação", quantidade=999,
                unidade="kg", data_movimento=date(2026, 1, 21),
            ))
            s.commit()

        r = c.get("/financeiro/rmca", params={"data_inicio": "2026-01-01", "data_fim": "2026-01-31"})
        assert r.status_code == 200
        fisico = r.json()["fisico"]
        assert fisico["receita_leite"] == 10000.0
        assert fisico["custo_alimentacao"] == 1000.0  # 400kg * R$2,50
        assert fisico["rmca"] == 9000.0
        assert fisico["itens"][0]["ingrediente"] == "Ração concentrada"
