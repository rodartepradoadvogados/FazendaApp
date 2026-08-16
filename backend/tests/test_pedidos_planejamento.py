"""
Testes de Pedidos e Planejamento (Orçamento + Planejamento financeiro):
- Pedido isolado não gera lançamento nem movimento de estoque.
- Vínculo de lançamento financeiro a um Pedido atualiza status/valor_atendido.
- Vínculo de entrada de estoque a um item de Pedido atualiza quantidade_atendida.
- Orçamento: CRUD + comparativo orçado x realizado.
- Planejamento financeiro: cenários + itens + projeção.
- Importar orçamento/planejamento para Pedido.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Estoque


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
        with Session(engine) as s:
            s.add(Estoque(nome="Sal mineral", quantidade=0, unidade="saca 30kg"))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


def _criar_pedido(client, **overrides):
    dados = {
        "tipo": "compra",
        "fornecedor_cliente": "Fornecedor Teste",
        "data_pedido": "2026-07-01",
        "itens": [{"tipo_item": "produto", "produto_servico": "Sal mineral", "valor_total_estimado": 1000.0}],
    }
    dados.update(overrides)
    return client.post("/pedidos/", json=dados)


class TestPedidosIsolamento:
    def test_criar_pedido_nao_gera_lancamento_nem_movimento(self, client):
        r = _criar_pedido(client)
        assert r.status_code == 201
        pedido_id = r.json()["id"]

        detalhe = client.get(f"/pedidos/{pedido_id}").json()
        assert detalhe["status"] == "aberto"
        assert detalhe["lancamentos"] == []
        assert detalhe["movimentos_estoque"] == []

        # Estoque continua zerado — pedido sozinho não mexe em Estoque.
        item = client.get("/estoque/").json()["itens"]
        sal = next(i for i in item if i["nome"] == "Sal mineral")
        assert sal["quantidade"] == 0

    def test_listar_pedidos_com_filtro_tipo(self, client):
        _criar_pedido(client)
        _criar_pedido(client, tipo="venda", fornecedor_cliente="Cliente Teste")
        r = client.get("/pedidos/", params={"tipo": "compra"})
        assert r.status_code == 200
        assert all(p["tipo"] == "compra" for p in r.json())

    def test_excluir_pedido_sem_vinculo_funciona(self, client):
        pedido_id = _criar_pedido(client).json()["id"]
        r = client.delete(f"/pedidos/{pedido_id}")
        assert r.status_code == 204
        assert client.get(f"/pedidos/{pedido_id}").status_code == 404


class TestRastreio:
    def test_marcar_enviado_grava_codigo_e_link(self, client):
        pedido_id = _criar_pedido(client).json()["id"]
        r = client.put(f"/pedidos/{pedido_id}/rastreio", json={
            "enviado": True, "codigo_rastreio": "BR123456789BR", "link_rastreio": "https://rastreio.correios.com.br/BR123456789BR",
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["enviado"] is True
        assert corpo["codigo_rastreio"] == "BR123456789BR"
        assert corpo["link_rastreio"] == "https://rastreio.correios.com.br/BR123456789BR"

        detalhe = client.get(f"/pedidos/{pedido_id}").json()
        assert detalhe["enviado"] is True
        assert detalhe["codigo_rastreio"] == "BR123456789BR"

    def test_marcar_nao_enviado_limpa_codigo_e_link(self, client):
        pedido_id = _criar_pedido(client).json()["id"]
        client.put(f"/pedidos/{pedido_id}/rastreio", json={
            "enviado": True, "codigo_rastreio": "BR123456789BR", "link_rastreio": "https://x.com/track",
        })
        r = client.put(f"/pedidos/{pedido_id}/rastreio", json={"enviado": False})
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["enviado"] is False
        assert corpo["codigo_rastreio"] is None
        assert corpo["link_rastreio"] is None


class TestVinculoFinanceiro:
    def test_lancamento_vinculado_atualiza_status_e_valor_atendido(self, client):
        pedido_id = _criar_pedido(client).json()["id"]

        r = client.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Sal mineral", "valor_total": 1000.0}],
            "data_emissao": "2026-07-05",
            "pedido_id": pedido_id,
        })
        assert r.status_code == 201

        detalhe = client.get(f"/pedidos/{pedido_id}").json()
        assert detalhe["status"] == "atendido"
        assert len(detalhe["lancamentos"]) == 1
        assert detalhe["itens"][0]["valor_atendido"] == 1000.0

    def test_lancamento_parcial_marca_status_intermediario(self, client):
        pedido_id = _criar_pedido(client).json()["id"]

        client.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Sal mineral", "valor_total": 400.0}],
            "data_emissao": "2026-07-05",
            "pedido_id": pedido_id,
        })
        detalhe = client.get(f"/pedidos/{pedido_id}").json()
        assert detalhe["status"] == "parcialmente_atendido"

    def test_lancamento_sem_pedido_id_nao_afeta_pedido(self, client):
        pedido_id = _criar_pedido(client).json()["id"]
        client.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Outra coisa", "valor_total": 50.0}],
            "data_emissao": "2026-07-05",
        })
        detalhe = client.get(f"/pedidos/{pedido_id}").json()
        assert detalhe["status"] == "aberto"
        assert detalhe["lancamentos"] == []

    def test_excluir_pedido_com_lancamento_vinculado_bloqueado(self, client):
        pedido_id = _criar_pedido(client).json()["id"]
        client.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Sal mineral", "valor_total": 1000.0}],
            "data_emissao": "2026-07-05",
            "pedido_id": pedido_id,
        })
        r = client.delete(f"/pedidos/{pedido_id}")
        assert r.status_code == 400


class TestVinculoEstoque:
    def test_entrada_vinculada_atualiza_quantidade_atendida(self, client):
        pedido_id = _criar_pedido(client).json()["id"]
        item_id = client.get(f"/pedidos/{pedido_id}").json()["itens"][0]["id"]

        r = client.post("/estoque/movimentar", json={
            "nome": "Sal mineral", "movimento": "Entrada de ajuste", "quantidade": 30,
            "data_movimento": "2026-07-06", "pedido_id": pedido_id, "pedido_item_id": item_id,
        })
        assert r.status_code == 200

        detalhe = client.get(f"/pedidos/{pedido_id}").json()
        assert detalhe["itens"][0]["quantidade_atendida"] == 30
        assert len(detalhe["movimentos_estoque"]) == 1

    def test_saida_com_pedido_item_id_nao_atualiza(self, client):
        # Saída não faz sentido "atender" um pedido de compra — só entrada conta.
        pedido_id = _criar_pedido(client).json()["id"]
        item_id = client.get(f"/pedidos/{pedido_id}").json()["itens"][0]["id"]
        client.post("/estoque/movimentar", json={
            "nome": "Sal mineral", "movimento": "Entrada de ajuste", "quantidade": 50,
            "data_movimento": "2026-07-06",
        })
        client.post("/estoque/movimentar", json={
            "nome": "Sal mineral", "movimento": "Saída de ajuste", "quantidade": 10,
            "data_movimento": "2026-07-07", "pedido_id": pedido_id, "pedido_item_id": item_id,
        })
        detalhe = client.get(f"/pedidos/{pedido_id}").json()
        assert detalhe["itens"][0]["quantidade_atendida"] == 0


class TestOrcamento:
    def test_crud_item_orcamento(self, client):
        r = client.post("/planejamento/orcamento", json={
            "ano": 2026, "mes": 8, "codigo_conta_gerencial": "3.01.01", "tipo": "despesa", "valor_orcado": 5000.0,
        })
        assert r.status_code == 201
        item_id = r.json()["id"]

        r = client.get("/planejamento/orcamento", params={"ano": 2026})
        assert r.status_code == 200
        assert len(r.json()) == 1

        r = client.put(f"/planejamento/orcamento/{item_id}", json={
            "ano": 2026, "mes": 8, "codigo_conta_gerencial": "3.01.01", "tipo": "despesa", "valor_orcado": 6000.0,
        })
        assert r.status_code == 200
        assert r.json()["valor_orcado"] == 6000.0

        assert client.delete(f"/planejamento/orcamento/{item_id}").status_code == 204
        assert client.get("/planejamento/orcamento", params={"ano": 2026}).json() == []

    def test_comparativo_orcado_realizado(self, client):
        client.post("/planejamento/orcamento", json={
            "ano": 2026, "mes": 7, "codigo_conta_gerencial": "3.01.01", "tipo": "despesa", "valor_orcado": 1000.0,
        })
        client.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"codigo_conta_gerencial": "3.01.01", "produto": "Sal mineral", "valor_total": 800.0}],
            "data_emissao": "2026-07-10", "data_competencia": "2026-07-10",
        })
        r = client.get("/planejamento/orcamento/comparativo", params={"ano": 2026, "mes_inicio": 7, "mes_fim": 7})
        assert r.status_code == 200
        corpo = r.json()
        linha = next(l for l in corpo["linhas"] if l["codigo_conta_gerencial"] == "3.01.01")
        assert linha["orcado"] == 1000.0
        assert linha["realizado"] == 800.0
        assert linha["desvio"] == -200.0


class TestPlanejamentoFinanceiro:
    def test_crud_cenario_e_itens_com_projecao(self, client):
        r = client.post("/planejamento/cenarios", json={"nome": "Expansão 2027", "tipo": "otimista"})
        assert r.status_code == 201
        cenario_id = r.json()["id"]

        r = client.post(f"/planejamento/cenarios/{cenario_id}/itens", json={
            "mes_competencia": "2027-01", "codigo_conta_gerencial": "2.01.01", "tipo": "receita", "valor_previsto": 10000.0,
        })
        assert r.status_code == 201
        r = client.post(f"/planejamento/cenarios/{cenario_id}/itens", json={
            "mes_competencia": "2027-01", "codigo_conta_gerencial": "3.01.01", "tipo": "despesa", "valor_previsto": 4000.0,
        })
        assert r.status_code == 201

        proj = client.get(f"/planejamento/cenarios/{cenario_id}/projecao").json()
        mes = proj["meses"][0]
        assert mes["receitas"] == 10000.0
        assert mes["despesas"] == 4000.0
        assert mes["saldo"] == 6000.0
        assert mes["acumulado"] == 6000.0

        assert client.delete(f"/planejamento/cenarios/{cenario_id}").status_code == 204
        assert client.get("/planejamento/cenarios").json() == []


class TestImportarParaPedido:
    def test_importar_orcamento_para_pedido(self, client):
        item = client.post("/planejamento/orcamento", json={
            "ano": 2026, "mes": 9, "codigo_conta_gerencial": "3.01.01", "tipo": "despesa", "valor_orcado": 2000.0,
        }).json()

        r = client.post("/planejamento/importar-para-pedido", json={
            "origem_tipo": "orcamento", "origem_item_id": item["id"], "tipo_pedido": "compra",
        })
        assert r.status_code == 201
        pedido_id = r.json()["id"]

        detalhe = client.get(f"/pedidos/{pedido_id}").json()
        assert detalhe["origem_tipo"] == "orcamento"
        assert detalhe["itens"][0]["valor_total_estimado"] == 2000.0
        # Importar não lança nada em Financeiro/Estoque.
        assert detalhe["lancamentos"] == []
        assert detalhe["movimentos_estoque"] == []
