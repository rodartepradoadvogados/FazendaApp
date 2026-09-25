"""
Cotação de Preços com Fornecedores — funcional + isolamento por fazenda.

Garante, na mesma bateria de testes que os demais módulos multi-fazenda já
seguem (ver test_financeiro_pedidos_planejamento_fazenda_isolamento.py):
duas fazendas podem usar o mesmo número de cotação sem conflitar, uma
fazenda não vê/edita/dispara/compara/gera pedidos a partir da cotação da
outra (404, não 403 — mesma convenção de IDOR), e — o ponto mais sensível
deste módulo — o link público que o fornecedor recebe NUNCA revela nem
altera dado de uma fazenda que não seja a dona daquele token, mesmo que a
requisição não carregue nenhuma credencial (ela literalmente não tem como
"pedir" outra fazenda, porque a fazenda vem só do token).
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")

import pytest
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, Fornecedor, FornecedorCategoria
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        # Um fornecedor por fazenda, mesma categoria, mesmo nome — pra provar
        # que a sugestão automática e a cotação nunca cruzam os dois.
        s.add(Fornecedor(id=1, fazenda_id=1, nome="Fornecedor X", tipo="fornecedor", email="x@f1.com", telefone="11999990001"))
        s.add(Fornecedor(id=2, fazenda_id=2, nome="Fornecedor X", tipo="fornecedor", email="x@f2.com", telefone="11999990002"))
        s.add(FornecedorCategoria(fornecedor_id=1, categoria="Ração e insumos alimentares", fazenda_id=1))
        s.add(FornecedorCategoria(fornecedor_id=2, categoria="Ração e insumos alimentares", fazenda_id=2))
        s.add(Estoque(id=1, fazenda_id=1, nome="Silagem", quantidade=100, unidade="saca"))
        s.add(Estoque(id=2, fazenda_id=2, nome="Silagem", quantidade=50, unidade="saca"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "admin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _payload(**overrides) -> dict:
    payload = {
        "categoria": "Ração e insumos alimentares",
        "modo": "completo",
        "prazo_resposta": "2026-12-31T18:00:00",
        "itens": [{"produto": "Silagem", "quantidade": 40.0, "unidade": "saca"}],
        "fornecedores": [{"fornecedor_id": overrides.pop("fornecedor_id", 1), "canal": "email"}],
    }
    payload.update(overrides)
    return payload


class TestFuncional:
    def test_criar_listar_obter(self, client):
        c, _ = client
        _como_fazenda(1)
        r = c.post("/cotacoes/", json=_payload())
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        assert r.json()["numero_cotacao"].startswith("COT-")

        listagem = c.get("/cotacoes/")
        assert listagem.status_code == 200
        assert len(listagem.json()) == 1
        assert listagem.json()[0]["total_fornecedores"] == 1

        detalhe = c.get(f"/cotacoes/{cid}")
        assert detalhe.status_code == 200
        assert detalhe.json()["status"] == "rascunho"
        assert len(detalhe.json()["itens"]) == 1
        assert detalhe.json()["itens"][0]["produto"] == "Silagem"
        assert detalhe.json()["fornecedores"][0]["fornecedor_nome"] == "Fornecedor X"

    def test_fluxo_completo_disparo_resposta_vencedor_gerar_pedido(self, client):
        c, _ = client
        _como_fazenda(1)
        cid = c.post("/cotacoes/", json=_payload()).json()["id"]

        # WhatsApp/e-mail não configurados neste teste -> falha_envio
        # esperada e registrada (não silenciosa), mas a cotação segue.
        disparo = c.post(f"/cotacoes/{cid}/disparar")
        assert disparo.status_code == 200, disparo.text
        assert disparo.json()["status"] == "enviada"
        assert disparo.json()["erros"]  # e-mail sem RESEND configurado -> falha registrada

        token = c.get(f"/cotacoes/{cid}").json()["fornecedores"][0]["token_publico"]

        # Fornecedor responde pela página pública, sem nenhuma credencial.
        item_id = c.get(f"/cotacoes/{cid}").json()["itens"][0]["id"]
        publica = c.get(f"/cotacao-publica/{token}")
        assert publica.status_code == 200
        assert publica.json()["numero_cotacao"] == c.get(f"/cotacoes/{cid}").json()["numero_cotacao"]

        resposta = c.post(f"/cotacao-publica/{token}/responder", json=[
            {"cotacao_item_id": item_id, "preco_unitario": 52.0, "frete_incluso": True, "prazo_entrega_dias": 4, "condicao_pagamento": "30 dias"},
        ])
        assert resposta.status_code == 200, resposta.text

        detalhe = c.get(f"/cotacoes/{cid}")
        assert detalhe.json()["status"] == "respondida"  # único fornecedor, já respondeu
        cotacao_fornecedor_id = detalhe.json()["fornecedores"][0]["id"]

        vencedores = c.put(f"/cotacoes/{cid}/vencedores", json=[
            {"cotacao_item_id": item_id, "cotacao_fornecedor_id": cotacao_fornecedor_id},
        ])
        assert vencedores.status_code == 200
        assert vencedores.json()["status"] == "comparada"

        gerar = c.post(f"/cotacoes/{cid}/gerar-pedidos")
        assert gerar.status_code == 201, gerar.text
        pedidos_gerados = gerar.json()["pedidos"]
        assert len(pedidos_gerados) == 1

        # O Pedido gerado é um Pedido DE VERDADE — aparece em /pedidos/.
        pedido_id = pedidos_gerados[0]["id"]
        pedido = c.get(f"/pedidos/{pedido_id}")
        assert pedido.status_code == 200
        assert pedido.json()["origem_tipo"] == "cotacao"
        assert pedido.json()["fornecedor_cliente"] == "Fornecedor X"
        assert pedido.json()["itens"][0]["quantidade"] == 40.0
        assert pedido.json()["itens"][0]["valor_unitario_estimado"] == 52.0

    def test_estoque_id_de_outra_fazenda_e_ignorado_na_criacao(self, client):
        c, _ = client
        _como_fazenda(1)
        # estoque_id=2 pertence à Fazenda Dois — não pode ser adotado.
        r = c.post("/cotacoes/", json=_payload(itens=[{"estoque_id": 2, "produto": "Silagem", "quantidade": 10, "unidade": "saca"}]))
        assert r.status_code == 201
        cid = r.json()["id"]
        item = c.get(f"/cotacoes/{cid}").json()["itens"][0]
        assert item["estoque_id"] is None


class TestIsolamentoAutenticado:
    def test_fazenda_2_nao_ve_cotacao_da_fazenda_1(self, client):
        c, _ = client
        _como_fazenda(1)
        cid = c.post("/cotacoes/", json=_payload()).json()["id"]

        _como_fazenda(2)
        assert c.get(f"/cotacoes/{cid}").status_code == 404
        assert c.get("/cotacoes/").json() == []
        assert c.post(f"/cotacoes/{cid}/disparar").status_code == 404
        assert c.put(f"/cotacoes/{cid}/vencedores", json=[]).status_code == 404
        assert c.post(f"/cotacoes/{cid}/gerar-pedidos").status_code == 404
        assert c.post(f"/cotacoes/{cid}/cancelar").status_code == 404
        assert c.delete(f"/cotacoes/{cid}").status_code == 404

    def test_duas_fazendas_podem_usar_o_mesmo_numero_de_cotacao(self, client):
        c, _ = client
        _como_fazenda(1)
        n1 = c.post("/cotacoes/", json=_payload()).json()["numero_cotacao"]
        _como_fazenda(2)
        n2 = c.post("/cotacoes/", json=_payload(fornecedor_id=2)).json()["numero_cotacao"]
        assert n1 == n2  # "COT-2026-00001" nas duas, sem colidir (UniqueConstraint é por fazenda)

    def test_sugestao_de_fornecedor_nao_cruza_fazenda(self, client):
        c, _ = client
        _como_fazenda(1)
        sugestoes = c.get("/cotacoes/opcoes/fornecedores-sugeridos", params={"categoria": "Ração e insumos alimentares"}).json()
        assert [f["id"] for f in sugestoes] == [1]

        _como_fazenda(2)
        sugestoes = c.get("/cotacoes/opcoes/fornecedores-sugeridos", params={"categoria": "Ração e insumos alimentares"}).json()
        assert [f["id"] for f in sugestoes] == [2]

    def test_nao_pode_criar_cotacao_com_fornecedor_de_outra_fazenda(self, client):
        c, _ = client
        _como_fazenda(1)
        # fornecedor_id=2 pertence à Fazenda Dois.
        r = c.post("/cotacoes/", json=_payload(fornecedor_id=2))
        assert r.status_code == 400


class TestIsolamentoPaginaPublica:
    """O ponto mais sensível do módulo: o fornecedor nunca envia nenhuma
    credencial de fazenda — a página pública tem que resolver e restringir
    TUDO a partir só do token, sem exceção."""

    def _cotacao_pronta_para_resposta(self, c, fazenda_id: int, fornecedor_id: int) -> tuple[str, int]:
        _como_fazenda(fazenda_id)
        cid = c.post("/cotacoes/", json=_payload(fornecedor_id=fornecedor_id)).json()["id"]
        c.post(f"/cotacoes/{cid}/disparar")
        detalhe = c.get(f"/cotacoes/{cid}").json()
        return detalhe["fornecedores"][0]["token_publico"], detalhe["itens"][0]["id"]

    def test_token_de_uma_fazenda_nunca_devolve_dado_de_outra(self, client):
        c, _ = client
        token_f1, _ = self._cotacao_pronta_para_resposta(c, 1, 1)

        # Um "atacante" logado como Fazenda Dois tenta ler o token da
        # Fazenda Um pela rota pública — a rota pública ignora completamente
        # qual fazenda está "selecionada" no token de sessão (ela nem
        # verifica), então o resultado tem que ser sempre o da Fazenda Um.
        _como_fazenda(2)
        publica = c.get(f"/cotacao-publica/{token_f1}")
        assert publica.status_code == 200
        assert publica.json()["nome_fazenda"] == "Fazenda Um"

    def test_token_invalido_nunca_vaza_nada(self, client):
        c, _ = client
        assert c.get("/cotacao-publica/token-que-nao-existe").status_code == 404
        assert c.post("/cotacao-publica/token-que-nao-existe/responder", json=[]).status_code == 404

    def test_responder_pelo_token_so_escreve_na_fazenda_dona_do_token(self, client):
        c, _ = client
        token_f1, item_f1 = self._cotacao_pronta_para_resposta(c, 1, 1)
        token_f2, item_f2 = self._cotacao_pronta_para_resposta(c, 2, 2)

        r = c.post(f"/cotacao-publica/{token_f1}/responder", json=[
            {"cotacao_item_id": item_f1, "preco_unitario": 10.0},
        ])
        assert r.status_code == 200

        # A resposta da Fazenda Um não pode aparecer na cotação da Fazenda
        # Dois nem ser lida por ela.
        _como_fazenda(2)
        cid_f2 = [c for c in c.get("/cotacoes/").json()][0]["id"]
        detalhe_f2 = c.get(f"/cotacoes/{cid_f2}")
        assert all(r["cotacao_item_id"] != item_f1 for r in detalhe_f2.json()["respostas"])

        _como_fazenda(1)
        cid_f1 = c.get("/cotacoes/").json()[0]["id"]
        detalhe_f1 = c.get(f"/cotacoes/{cid_f1}")
        assert any(r["cotacao_item_id"] == item_f1 and r["preco_unitario"] == 10.0 for r in detalhe_f1.json()["respostas"])

    def test_responder_com_item_de_outra_cotacao_e_recusado(self, client):
        c, _ = client
        token_f1, _ = self._cotacao_pronta_para_resposta(c, 1, 1)
        _, item_f2 = self._cotacao_pronta_para_resposta(c, 2, 2)

        r = c.post(f"/cotacao-publica/{token_f1}/responder", json=[
            {"cotacao_item_id": item_f2, "preco_unitario": 10.0},
        ])
        assert r.status_code == 400


class TestPedidoFormalPublico:
    def _pedido_gerado_via_cotacao(self, c) -> int:
        _como_fazenda(1)
        cid = c.post("/cotacoes/", json=_payload()).json()["id"]
        c.post(f"/cotacoes/{cid}/disparar")
        detalhe = c.get(f"/cotacoes/{cid}").json()
        token = detalhe["fornecedores"][0]["token_publico"]
        item_id = detalhe["itens"][0]["id"]
        c.post(f"/cotacao-publica/{token}/responder", json=[{"cotacao_item_id": item_id, "preco_unitario": 52.0}])
        detalhe = c.get(f"/cotacoes/{cid}").json()
        cf_id = detalhe["fornecedores"][0]["id"]
        c.put(f"/cotacoes/{cid}/vencedores", json=[{"cotacao_item_id": item_id, "cotacao_fornecedor_id": cf_id}])
        pedido_id = c.post(f"/cotacoes/{cid}/gerar-pedidos").json()["pedidos"][0]["id"]
        return pedido_id

    def test_disparar_pedido_formal_e_confirmar_pelo_token(self, client):
        c, _ = client
        pedido_id = self._pedido_gerado_via_cotacao(c)

        disparo = c.post(f"/pedidos/{pedido_id}/confirmacao")
        assert disparo.status_code == 200, disparo.text
        token = disparo.json()["token"]
        assert token

        # Fornecedor abre o link sem nenhuma credencial.
        publica = c.get(f"/pedido-confirmacao-publica/{token}")
        assert publica.status_code == 200
        assert publica.json()["fazenda"]["nome"] == "Fazenda Um"

        confirmar = c.post(f"/pedido-confirmacao-publica/{token}/confirmar", json={"previsao_entrega": "5 dias úteis"})
        assert confirmar.status_code == 200
        assert confirmar.json()["status"] == "confirmado"

        # Segunda confirmação no mesmo token é recusada (já respondido).
        assert c.post(f"/pedido-confirmacao-publica/{token}/confirmar", json={}).status_code == 400

    def test_dados_de_faturamento_da_fazenda_aparecem_na_pagina_publica(self, client):
        c, engine = client
        with Session(engine) as s:
            fazenda = s.get(Fazenda, 1)
            fazenda.tipo_documento = "cnpj"
            fazenda.documento = "12.345.678/0001-90"
            fazenda.inscricao_estadual = "123.456.789.000"
            fazenda.endereco = "Rod. BR-364, km 12"
            s.add(fazenda)
            s.commit()

        pedido_id = self._pedido_gerado_via_cotacao(c)
        token = c.post(f"/pedidos/{pedido_id}/confirmacao").json()["token"]
        dados = c.get(f"/pedido-confirmacao-publica/{token}").json()["fazenda"]
        assert dados["documento"] == "12.345.678/0001-90"
        assert dados["inscricao_estadual"] == "123.456.789.000"

    def test_token_de_pedido_de_uma_fazenda_nao_vaza_para_outra(self, client):
        c, _ = client
        pedido_id_f1 = self._pedido_gerado_via_cotacao(c)
        token_f1 = c.post(f"/pedidos/{pedido_id_f1}/confirmacao").json()["token"]

        _como_fazenda(2)
        # Mesmo "logada" como Fazenda Dois, a rota pública devolve o dado da
        # Fazenda Um (dona do token) — nunca mistura, nunca recusa por
        # "fazenda errada" (a rota pública não tem esse conceito).
        publica = c.get(f"/pedido-confirmacao-publica/{token_f1}")
        assert publica.status_code == 200
        assert publica.json()["fazenda"]["nome"] == "Fazenda Um"

        # E o disparo/confirmação não pode ser acionado por quem não é dono
        # do Pedido de verdade (rota autenticada).
        assert c.post(f"/pedidos/{pedido_id_f1}/confirmacao").status_code == 404
