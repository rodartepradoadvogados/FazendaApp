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
from fazenda.models import CentroCusto, ContaCorrente, ContaGerencial, Estoque, LancamentoItem, MovimentoEstoque, ParametroFazenda, PlanoContaGerencial
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
def client(monkeypatch):
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

    # Fake do Supabase Storage (anexos de lançamento) — guarda em memória em
    # vez de falar de verdade com o Supabase, mesmo padrão de
    # test_arquivo_contador_desbloqueio.py, mas com um "bucket" fake de
    # verdade (dict) para os testes que conferem o conteúdo baixado.
    import fazenda.api.routers.financeiro as financeiro_mod
    _bucket_fake: dict[str, bytes] = {}
    monkeypatch.setattr(financeiro_mod, "enviar_arquivo", lambda caminho, conteudo, *a, **k: _bucket_fake.__setitem__(caminho, conteudo))
    monkeypatch.setattr(financeiro_mod, "baixar_arquivo", lambda caminho, *a, **k: _bucket_fake[caminho])
    monkeypatch.setattr(financeiro_mod, "excluir_arquivo", lambda caminho, *a, **k: _bucket_fake.pop(caminho, None))

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


class TestCentroCustoObrigatorio:
    """#504 — todo lançamento deve nascer com um centro de custo; quando o
    caller (CSV, robô) não informa, assume "Pecuária Leiteira" em vez de
    deixar a conta sem centro (nunca fica None/vazio no banco)."""

    def test_lancamento_sem_centro_custo_assume_pecuaria_leiteira(self, client):
        c, engine = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "X", "valor_total": 100.0}],
        })
        assert r.status_code == 201
        with Session(engine) as s:
            from sqlmodel import select
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == r.json()["numero_lancamento"])).first()
            assert conta.centro_custo == "Pecuária Leiteira"

    def test_lancamento_com_centro_custo_informado_preserva_escolha(self, client):
        c, engine = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "X", "valor_total": 100.0}],
            "centro_custo": "Arrendamento",
        })
        assert r.status_code == 201
        with Session(engine) as s:
            from sqlmodel import select
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == r.json()["numero_lancamento"])).first()
            assert conta.centro_custo == "Arrendamento"

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


class TestNumeroOsOrcamentoENumeroBoleto:
    """Nº da OS/orçamento é um campo de consulta à parte do nº do documento;
    nº do boleto é opcional e vale por parcela (cada parcela pode ter o seu)."""

    def test_numero_documento_e_numero_os_orcamento_sao_campos_distintos(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Peças", "valor_total": 400.0}],
            "numero_documento": "NF-1234",
            "numero_os_orcamento": "OS-777",
        })
        assert r.status_code == 201
        numero = r.json()["numero_lancamento"]
        registro = next(l for l in c.get("/financeiro/lancamentos").json()["lancamentos"] if l["numero_lancamento"] == numero)
        assert registro["numero_documento"] == "NF-1234"
        assert registro["numero_os_orcamento"] == "OS-777"

    def test_numero_boleto_por_parcela_no_lancamento_parcelado(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Insumo", "valor_total": 1200.0}],
            "parcelas": [
                {"data_vencimento": "2026-08-10", "valor": 600.0, "numero_boleto": "111.11"},
                {"data_vencimento": "2026-09-10", "valor": 600.0, "numero_boleto": "222.22"},
            ],
        })
        assert r.status_code == 201
        numero = r.json()["numero_lancamento"]
        parcelas = sorted(
            (l for l in c.get("/financeiro/lancamentos").json()["lancamentos"] if l["numero_lancamento"] == numero),
            key=lambda l: l["parcela_num"],
        )
        assert [p["numero_boleto"] for p in parcelas] == ["111.11", "222.22"]

    def test_edicao_do_lancamento_atualiza_os_orcamento_e_numero_boleto(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={"tipo": "despesa", "itens": [{"produto": "X", "valor_total": 100.0}]})
        lanc_id = r.json()["ids"][0]
        r2 = c.put(f"/financeiro/lancamentos/{lanc_id}", json={"numero_os_orcamento": "ORC-55", "numero_boleto": "999"})
        assert r2.status_code == 200
        assert r2.json()["numero_os_orcamento"] == "ORC-55"
        assert r2.json()["numero_boleto"] == "999"


class TestAnexosLancamento:
    def _criar_lancamento(self, c) -> str:
        r = c.post("/financeiro/lancamentos", json={"tipo": "despesa", "itens": [{"produto": "Insumo", "valor_total": 500.0}]})
        return r.json()["numero_lancamento"]

    def test_anexa_e_lista_arquivo(self, client):
        c, _ = client
        numero = self._criar_lancamento(c)
        r = c.post(f"/financeiro/lancamentos/{numero}/anexos", files={"file": ("boleto.pdf", b"%PDF-1.4 conteudo", "application/pdf")})
        assert r.status_code == 201
        assert r.json()["nome_arquivo"] == "boleto.pdf"

        listagem = c.get(f"/financeiro/lancamentos/{numero}/anexos").json()
        assert len(listagem) == 1
        assert listagem[0]["mime_type"] == "application/pdf"

    def test_anexa_varios_arquivos_ao_mesmo_lancamento(self, client):
        c, _ = client
        numero = self._criar_lancamento(c)
        for i in range(3):
            r = c.post(f"/financeiro/lancamentos/{numero}/anexos", files={"file": (f"boleto{i}.pdf", b"conteudo", "application/pdf")})
            assert r.status_code == 201
        assert len(c.get(f"/financeiro/lancamentos/{numero}/anexos").json()) == 3

    def test_anexo_de_lancamento_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos/LC-9999-99999/anexos", files={"file": ("x.pdf", b"conteudo", "application/pdf")})
        assert r.status_code == 404

    def test_baixa_o_conteudo_do_anexo(self, client):
        c, _ = client
        numero = self._criar_lancamento(c)
        conteudo = b"%PDF-1.4 conteudo do boleto"
        anexo_id = c.post(f"/financeiro/lancamentos/{numero}/anexos", files={"file": ("boleto.pdf", conteudo, "application/pdf")}).json()["id"]
        r = c.get(f"/financeiro/anexos/{anexo_id}")
        assert r.status_code == 200
        assert r.content == conteudo
        assert r.headers["content-type"] == "application/pdf"

    def test_exclui_anexo(self, client):
        c, _ = client
        numero = self._criar_lancamento(c)
        anexo_id = c.post(f"/financeiro/lancamentos/{numero}/anexos", files={"file": ("boleto.pdf", b"conteudo", "application/pdf")}).json()["id"]
        assert c.delete(f"/financeiro/anexos/{anexo_id}").status_code == 200
        assert c.get(f"/financeiro/anexos/{anexo_id}").status_code == 404
        assert c.get(f"/financeiro/lancamentos/{numero}/anexos").json() == []

    def test_categoria_explicita_e_gravada(self, client):
        c, _ = client
        numero = self._criar_lancamento(c)
        r = c.post(
            f"/financeiro/lancamentos/{numero}/anexos",
            data={"categoria": "Nota fiscal"},
            files={"file": ("nf.pdf", b"conteudo", "application/pdf")},
        )
        assert r.json()["categoria"] == "Nota fiscal"
        assert c.get(f"/financeiro/lancamentos/{numero}/anexos").json()[0]["categoria"] == "Nota fiscal"

    def test_sem_categoria_explicita_herda_tipo_documento_do_lancamento(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "tipo_documento": "Recibo", "itens": [{"produto": "Insumo", "valor_total": 500.0}],
        })
        numero = r.json()["numero_lancamento"]
        r = c.post(f"/financeiro/lancamentos/{numero}/anexos", files={"file": ("x.pdf", b"conteudo", "application/pdf")})
        assert r.json()["categoria"] == "Recibo"

    def test_anexo_legado_sem_caminho_storage_continua_baixavel(self, client):
        """Anexo já existente antes da migração pro Supabase (conteudo em
        bytes no Postgres, sem caminho_storage) — precisa continuar sendo
        baixado normalmente, sem tentar falar com o Supabase."""
        c, engine = client
        from fazenda.models import LancamentoAnexo
        numero = self._criar_lancamento(c)
        with Session(engine) as s:
            legado = LancamentoAnexo(
                numero_lancamento=numero, nome_arquivo="antigo.pdf", mime_type="application/pdf",
                tamanho_bytes=7, conteudo=b"legado!",
            )
            s.add(legado); s.commit(); s.refresh(legado)
            anexo_id = legado.id
        r = c.get(f"/financeiro/anexos/{anexo_id}")
        assert r.status_code == 200
        assert r.content == b"legado!"


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
        assert corpo["meta_rmca"] == 0  # padrão — preserva o "verde se >= 0" de antes

    def test_meta_rmca_reage_ao_parametro_configurado(self, client, monkeypatch):
        c, engine = client
        # get_param()/_linha() lê `fazenda.database.engine` diretamente (não
        # via Depends) — sem isso, a leitura pós-PUT cairia no engine
        # padrão do módulo, não no engine isolado deste teste.
        monkeypatch.setattr(database, "engine", engine)
        with Session(engine) as s:
            self._marcar_contas(s)
            s.add(ParametroFazenda(chave="meta_rmca", grupo="financeiro",
                                    label="RMCA mínimo aceitável", valor="0", tipo="float", unidade="R$"))
            s.commit()
        assert c.put("/parametros/meta_rmca", json={"valor": 5000.0}).status_code == 200
        r = c.get("/financeiro/rmca", params={"data_inicio": "2026-01-01", "data_fim": "2026-01-31"})
        assert r.json()["meta_rmca"] == 5000.0

    def test_versao_fisica_usa_consumo_real_x_valor_unitario_do_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            self._marcar_contas(s)
            s.add(Estoque(nome="Ração concentrada", quantidade=1000, unidade="kg", valor_unitario=2.5,
                           conta_gerencial_despesa_padrao="3.01.01"))
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

    def test_versao_fisica_exclui_item_fora_da_conta_gerencial_alimentacao(self, client):
        c, engine = client
        with Session(engine) as s:
            self._marcar_contas(s)
            s.add(Estoque(nome="Ração concentrada", quantidade=1000, unidade="kg", valor_unitario=2.5,
                           conta_gerencial_despesa_padrao="3.01.01"))
            s.add(Estoque(nome="Medicamento X", quantidade=100, unidade="un", valor_unitario=10.0,
                           conta_gerencial_despesa_padrao="3.02.01"))
            s.commit()

        with Session(engine) as s:
            s.add(MovimentoEstoque(
                nome_item="Ração concentrada", movimento="Saída de ajuste", quantidade=400,
                unidade="kg", data_movimento=date(2026, 1, 20),
            ))
            # Item de conta gerencial diferente de "3.01.01" — não deve entrar no
            # custo físico mesmo tendo baixa de "Saída de ajuste" no período.
            s.add(MovimentoEstoque(
                nome_item="Medicamento X", movimento="Saída de ajuste", quantidade=5,
                unidade="un", data_movimento=date(2026, 1, 22),
            ))
            s.commit()

        r = c.get("/financeiro/rmca", params={"data_inicio": "2026-01-01", "data_fim": "2026-01-31"})
        assert r.status_code == 200
        fisico = r.json()["fisico"]
        assert fisico["custo_alimentacao"] == 1000.0  # só a Ração — o Medicamento X ficou de fora
        assert [i["ingrediente"] for i in fisico["itens"]] == ["Ração concentrada"]


class TestBaixaLoteDetalhada:
    """Baixa em lote com pagamento diferente por nota (data/valor/conta/forma
    por linha)."""

    def _criar(self, c, valor):
        return c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração", "quantidade": 1, "valor_unitario": valor, "valor_total": valor}],
        }).json()["ids"][0]

    def test_cada_nota_com_seu_proprio_pagamento(self, client):
        c, engine = client
        id1 = self._criar(c, 500.0)
        id2 = self._criar(c, 800.0)
        r = c.put("/financeiro/lancamentos/baixa-lote-detalhada", json={"itens": [
            {"lancamento_id": id1, "data_pagamento": "2026-07-08", "valor_pago": 500.0, "conta_bancaria": "Banco A", "forma_pagamento": "pix"},
            {"lancamento_id": id2, "data_pagamento": "2026-07-10", "valor_pago": 780.0, "conta_bancaria": "Banco B", "forma_pagamento": "dinheiro"},
        ]})
        assert r.status_code == 200 and r.json()["baixados"] == 2
        lancs = {l["id"]: l for l in c.get("/financeiro/lancamentos").json()["lancamentos"]}
        assert lancs[id1]["data_pagamento"] == "2026-07-08" and lancs[id1]["conta_bancaria"] == "Banco A"
        assert lancs[id2]["data_pagamento"] == "2026-07-10" and lancs[id2]["conta_bancaria"] == "Banco B"
        assert lancs[id2]["valor_pago"] == 780.0
        # Valor pago menor que o total vira desconto (−20).
        assert lancs[id2]["desconto_acrescimo"] == -20.0

    def test_credito_por_linha_exige_vencimento(self, client):
        c, engine = client
        id1 = self._criar(c, 300.0)
        r = c.put("/financeiro/lancamentos/baixa-lote-detalhada", json={"itens": [
            {"lancamento_id": id1, "data_pagamento": "2026-07-08", "valor_pago": 300.0, "forma_pagamento": "credito"},
        ]})
        assert r.status_code == 400

    def test_sem_itens_da_erro(self, client):
        c, engine = client
        r = c.put("/financeiro/lancamentos/baixa-lote-detalhada", json={"itens": []})
        assert r.status_code == 400


class TestReciboLancamento:
    """#505 — emissão de recibo: destinatário contextual (Fornecedor/Pessoa
    pelo nome) e envio por e-mail (Resend, mockado nos testes)."""

    def test_destinatario_resolve_por_fornecedor(self, client):
        c, engine = client
        with Session(engine) as s:
            from fazenda.models import Fornecedor
            s.add(Fornecedor(nome="Cooperativa Agro LTDA", tipo="fornecedor", email="contato@agro.com"))
            s.commit()
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "fornecedor_cliente": "Cooperativa Agro LTDA",
            "itens": [{"produto": "Ração", "valor_total": 500.0}],
        })
        numero = r.json()["numero_lancamento"]
        resp = c.get(f"/financeiro/lancamentos/{numero}/destinatario-recibo")
        assert resp.status_code == 200
        assert resp.json() == {"nome": "Cooperativa Agro LTDA", "email": "contato@agro.com"}

    def test_destinatario_resolve_por_pessoa_na_folha_de_pagamento(self, client):
        """Folha de pagamento busca o e-mail em Pessoa (não Fornecedor) — e
        continua funcionando com o cadastro de múltiplos e-mails (#511): o
        recibo usa sempre o primeiro e-mail da lista."""
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={
            "nome": "Funcionário Recibo", "tipos": ["Funcionário"],
            "emails": ["principal@x.com", "secundario@x.com"],
        }).json()["id"]
        c.post("/cadastro/folha-pagamento", json={"pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 1000.0})
        with Session(engine) as s:
            from sqlmodel import select
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Folha de pagamento")).first()
        resp = c.get(f"/financeiro/lancamentos/{conta.numero_lancamento}/destinatario-recibo")
        assert resp.status_code == 200
        assert resp.json() == {"nome": "Funcionário Recibo", "email": "principal@x.com"}

    def test_destinatario_sem_cadastro_devolve_email_vazio(self, client):
        c, engine = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "fornecedor_cliente": "Fulano Desconhecido",
            "itens": [{"produto": "X", "valor_total": 10.0}],
        })
        numero = r.json()["numero_lancamento"]
        resp = c.get(f"/financeiro/lancamentos/{numero}/destinatario-recibo")
        assert resp.json() == {"nome": "Fulano Desconhecido", "email": None}

    def test_enviar_recibo_sem_resend_configurado_da_erro_claro(self, client):
        c, engine = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "fornecedor_cliente": "X",
            "itens": [{"produto": "X", "valor_total": 10.0}],
        })
        numero = r.json()["numero_lancamento"]
        resp = c.post(
            f"/financeiro/lancamentos/{numero}/recibo/enviar",
            data={"destinatario": "alguem@exemplo.com"},
            files={"arquivo": ("recibo.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "RESEND_API_KEY" in resp.json()["detail"]

    def test_enviar_recibo_com_envio_mockado(self, client, monkeypatch):
        c, engine = client
        from fazenda.api.routers import financeiro as financeiro_router
        chamadas = []
        monkeypatch.setattr(
            financeiro_router, "enviar_email",
            lambda destinatario, assunto, corpo_html, anexo_nome, anexo_bytes: chamadas.append(destinatario),
        )
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "fornecedor_cliente": "X",
            "itens": [{"produto": "X", "valor_total": 10.0}],
        })
        numero = r.json()["numero_lancamento"]
        resp = c.post(
            f"/financeiro/lancamentos/{numero}/recibo/enviar",
            data={"destinatario": "alguem@exemplo.com"},
            files={"arquivo": ("recibo.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert resp.status_code == 200 and resp.json() == {"enviado": True}
        assert chamadas == ["alguem@exemplo.com"]


class TestLancamentoRecorrente:
    """Modelo de conta recorrente (energia/internet/telefone/assinatura/
    aluguel) — cadastra os dados fixos uma vez, gera um LancamentoFinanceiro
    de verdade a cada período só com os dados variáveis (valor, emissão,
    boleto)."""

    def _criar_modelo(self, c, **overrides):
        payload = {
            "descricao": "Energia CPFL",
            "tipo": "despesa",
            "fornecedor_cliente": "CPFL Energia",
            "centro_custo": "Pecuária Leiteira",
            "codigo_conta_gerencial": "3.03.02.11",
            "nome_conta_gerencial": "Energia elétrica",
            "tipo_item": "servico",
            "forma_pagamento_padrao": "boleto",
            "conta_bancaria_padrao": "Banco do Brasil · Agência 3775-3 · Conta corrente 3.615-3",
            "dia_vencimento": 10,
            "periodicidade": "mensal",
        }
        payload.update(overrides)
        return c.post("/financeiro/recorrentes", json=payload)

    def test_cria_modelo_recorrente(self, client):
        c, _ = client
        r = self._criar_modelo(c)
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["descricao"] == "Energia CPFL"
        assert corpo["dia_vencimento"] == 10
        assert corpo["ativo"] is True
        assert corpo["ultimo_numero_lancamento"] is None

    def test_rejeita_tipo_invalido(self, client):
        c, _ = client
        r = self._criar_modelo(c, tipo="outro")
        assert r.status_code == 400

    def test_rejeita_periodicidade_nao_suportada(self, client):
        c, _ = client
        r = self._criar_modelo(c, periodicidade="anual")
        assert r.status_code == 400

    def test_rejeita_dia_vencimento_fora_do_intervalo(self, client):
        c, _ = client
        r = self._criar_modelo(c, dia_vencimento=32)
        assert r.status_code == 400

    def test_listar_recorrentes(self, client):
        c, _ = client
        self._criar_modelo(c)
        self._criar_modelo(c, descricao="Internet Vivo Fibra")
        r = c.get("/financeiro/recorrentes")
        assert r.status_code == 200
        nomes = {m["descricao"] for m in r.json()}
        assert nomes == {"Energia CPFL", "Internet Vivo Fibra"}

    def test_atualizar_modelo_recorrente(self, client):
        c, _ = client
        modelo_id = self._criar_modelo(c).json()["id"]
        r = c.put(f"/financeiro/recorrentes/{modelo_id}", json={
            "descricao": "Energia CPFL", "tipo": "despesa", "dia_vencimento": 15, "ativo": False,
        })
        assert r.status_code == 200
        assert r.json()["dia_vencimento"] == 15
        assert r.json()["ativo"] is False

    def test_atualizar_modelo_inexistente_da_404(self, client):
        c, _ = client
        r = c.put("/financeiro/recorrentes/9999", json={"descricao": "X", "tipo": "despesa"})
        assert r.status_code == 404

    def test_gerar_lancamento_a_partir_do_modelo(self, client):
        c, engine = client
        modelo_id = self._criar_modelo(c).json()["id"]
        r = c.post(f"/financeiro/recorrentes/{modelo_id}/gerar", json={
            "valor": 842.37, "data_emissao": "2026-08-05", "numero_boleto": "34191.12345 67890.123456",
        })
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["valor_liquido"] == 842.37
        numero = corpo["numero_lancamento"]

        # É um LancamentoFinanceiro normal — aparece no extrato como qualquer outro.
        listagem = c.get("/financeiro/lancamentos").json()["lancamentos"]
        registro = next(l for l in listagem if l["numero_lancamento"] == numero)
        assert registro["tipo"] == "despesa"
        assert registro["valor"] == 842.37
        assert registro["fornecedor"] == "CPFL Energia"
        assert registro["centro_custo"] == "Pecuária Leiteira"
        assert registro["numero_boleto"] == "34191.12345 67890.123456"
        assert registro["data_emissao"] == "2026-08-05"
        # Vencimento calculado a partir do dia_vencimento do modelo (10) — mês
        # da emissão informada (agosto/2026), não o mês corrente do teste.
        assert registro["data_vencimento"] == "2026-08-10"
        assert registro["data_pagamento"] is None  # nasce em aberto, sem ja_pago
        assert len(registro["itens"]) == 1
        assert registro["itens"][0]["produto"] == "Energia CPFL"
        assert registro["itens"][0]["codigo_conta_gerencial"] == "3.03.02.11"

        # O modelo guarda o rastro do último lançamento gerado.
        modelo = c.get("/financeiro/recorrentes").json()[0]
        assert modelo["ultimo_numero_lancamento"] == numero
        assert modelo["ultima_geracao_em"] is not None

    def test_gerar_vencimento_ajustado_no_fim_do_mes(self, client):
        c, _ = client
        modelo_id = self._criar_modelo(c, dia_vencimento=31).json()["id"]
        r = c.post(f"/financeiro/recorrentes/{modelo_id}/gerar", json={
            "valor": 100.0, "data_emissao": "2026-02-03",
        })
        assert r.status_code == 201
        numero = r.json()["numero_lancamento"]
        registro = next(l for l in c.get("/financeiro/lancamentos").json()["lancamentos"] if l["numero_lancamento"] == numero)
        assert registro["data_vencimento"] == "2026-02-28"  # fevereiro/2026 não é bissexto

    def test_gerar_ja_pago_usa_forma_e_conta_padrao_do_modelo(self, client):
        c, _ = client
        modelo_id = self._criar_modelo(c).json()["id"]
        r = c.post(f"/financeiro/recorrentes/{modelo_id}/gerar", json={
            "valor": 300.0, "data_emissao": "2026-08-05", "ja_pago": True, "data_pagamento": "2026-08-06",
        })
        assert r.status_code == 201
        numero = r.json()["numero_lancamento"]
        registro = next(l for l in c.get("/financeiro/lancamentos").json()["lancamentos"] if l["numero_lancamento"] == numero)
        assert registro["data_pagamento"] == "2026-08-06"
        assert registro["valor_pago"] == 300.0
        assert registro["forma_pagamento"] == "boleto"
        assert registro["conta_bancaria"] == "Banco do Brasil · Agência 3775-3 · Conta corrente 3.615-3"

    def test_gerar_a_partir_de_modelo_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/financeiro/recorrentes/9999/gerar", json={"valor": 100.0})
        assert r.status_code == 404

    def test_gerar_com_valor_zero_ou_negativo_da_erro(self, client):
        c, _ = client
        modelo_id = self._criar_modelo(c).json()["id"]
        r = c.post(f"/financeiro/recorrentes/{modelo_id}/gerar", json={"valor": 0})
        assert r.status_code == 400


class TestSupabaseDashboardUrl:
    def test_sem_config_devolve_url_nula(self, client):
        c, _ = client
        r = c.get("/financeiro/supabase-dashboard-url")
        assert r.status_code == 200
        assert r.json()["url"] is None

    def test_deriva_url_do_supabase_url_configurado(self, client, monkeypatch):
        c, _ = client
        from fazenda.config import settings
        monkeypatch.setattr(settings, "supabase_url", "https://abcdefgh.supabase.co")
        r = c.get("/financeiro/supabase-dashboard-url")
        assert r.status_code == 200
        assert r.json()["url"] == "https://supabase.com/dashboard/project/abcdefgh/editor"
