"""
Testes de `PUT /pedidos/{pedido_id}/itens/{item_id}/entrega` — marcação de
entrega física por item (passo 2 do redesenho de Pedidos, ver
`fazenda/rules/pedido_status.py` e `PedidoItem.quantidade_entregue`, ambos do
passo 1).

Cobre: status recalculado (parcial/atendido) a partir de
`calcular_status_pedido`; entrada automática de estoque só para item
"produto" com aumento de `quantidade_entregue` (Decisão A1), usando as
colunas dedicadas `MovimentoEstoque.pedido_id`/`pedido_item_id`; item
"servico" nunca mexe em estoque; pendências de fechamento financeiro
(`pagamento`/`data_emissao`) quando não há `ContaGerencial` vinculado;
pedido cancelado é terminal e recusa marcação de entrega; isolamento por
`fazenda_id`.

Arquivo autocontido, seguindo o padrão de `test_isolamento_animal.py`/
`test_curva_referencia_grupo_ordem_parto.py` (fixture `client` + `_como_fazenda`).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, MovimentoEstoque


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    # `pedidos.router` exige o módulo comercial "pedidos" contratado e ativo
    # pela fazenda sempre que get_fazenda_atual_id devolve um id não-nulo
    # (ver main.py: exigir_modulo_contratado("pedidos")) — precisa dos dois
    # contratos (fazendas 1 e 2) para o teste de isolamento, mesmo padrão de
    # test_curva_referencia_grupo_ordem_parto.py.
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="pedidos", preco=0.0, ativo=True))
        # Item de estoque casável por nome com o PedidoItem "produto" usado
        # nos testes abaixo (ver `estoque_baixa.resolver_item`) — unidade
        # preenchida de propósito: sem ela `pode_dar_baixa_direta` recusa a
        # baixa (ver comentário em fazenda/rules/unidades.py).
        s.add(Estoque(nome="Sal mineral", quantidade=0, unidade="saca", fazenda_id=1))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _criar_pedido(client, itens, **overrides):
    dados = {
        "tipo": "compra",
        "fornecedor_cliente": "Fornecedor Teste",
        "data_pedido": "2026-08-01",
        "itens": itens,
    }
    dados.update(overrides)
    r = client.post("/pedidos/", json=dados)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _itens_do_pedido(client, pedido_id: int) -> dict[str, dict]:
    """Mapa produto_servico -> item (dict) do GET /pedidos/{id} — evita
    depender de ordem/posição do array."""
    r = client.get(f"/pedidos/{pedido_id}")
    assert r.status_code == 200
    return {i["produto_servico"]: i for i in r.json()["itens"]}


class TestStatusPorEntrega:
    def test_marcar_entrega_parcial_de_um_item_deixa_pedido_parcialmente_atendido(self, client):
        c, _ = client
        pedido_id = _criar_pedido(c, [
            {"tipo_item": "produto", "produto_servico": "Sal mineral", "quantidade": 10, "valor_total_estimado": 500.0},
            {"tipo_item": "servico", "produto_servico": "Frete", "quantidade": 1, "valor_total_estimado": 100.0},
        ])
        item_id = _itens_do_pedido(c, pedido_id)["Sal mineral"]["id"]

        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 4})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "parcialmente_atendido"

        r = c.get(f"/pedidos/{pedido_id}")
        assert r.json()["status"] == "parcialmente_atendido"

    def test_marcar_entrega_completa_de_todos_os_itens_deixa_pedido_atendido(self, client):
        c, _ = client
        pedido_id = _criar_pedido(c, [
            {"tipo_item": "produto", "produto_servico": "Sal mineral", "quantidade": 10, "valor_total_estimado": 500.0},
            {"tipo_item": "servico", "produto_servico": "Frete", "quantidade": 1, "valor_total_estimado": 100.0},
        ])
        itens = _itens_do_pedido(c, pedido_id)

        r = c.put(f"/pedidos/{pedido_id}/itens/{itens['Sal mineral']['id']}/entrega", json={"quantidade_entregue": 10})
        assert r.status_code == 200
        assert r.json()["status"] == "parcialmente_atendido"  # falta o serviço

        r = c.put(f"/pedidos/{pedido_id}/itens/{itens['Frete']['id']}/entrega", json={"quantidade_entregue": 1})
        assert r.status_code == 200
        assert r.json()["status"] == "atendido"

        r = c.get(f"/pedidos/{pedido_id}")
        assert r.json()["status"] == "atendido"


class TestEntradaAutomaticaDeEstoque:
    def test_item_produto_gera_movimento_estoque_com_pedido_id_e_soma_saldo(self, client):
        c, engine = client
        pedido_id = _criar_pedido(c, [
            {"tipo_item": "produto", "produto_servico": "Sal mineral", "quantidade": 12, "valor_total_estimado": 600.0},
        ])
        item_id = _itens_do_pedido(c, pedido_id)["Sal mineral"]["id"]

        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 12})
        assert r.status_code == 200, r.text
        assert r.json()["avisos_estoque"] == []

        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Sal mineral")).first()
            assert estoque.quantidade == 12

            movimentos = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.pedido_id == pedido_id)).all()
            assert len(movimentos) == 1
            mov = movimentos[0]
            assert mov.pedido_item_id == item_id
            assert mov.movimento == "Entrada de compra"
            assert mov.quantidade == 12
            assert mov.estoque_id == estoque.id

    def test_entrega_parcial_depois_completa_gera_dois_movimentos_só_com_o_delta(self, client):
        c, engine = client
        pedido_id = _criar_pedido(c, [
            {"tipo_item": "produto", "produto_servico": "Sal mineral", "quantidade": 12, "valor_total_estimado": 600.0},
        ])
        item_id = _itens_do_pedido(c, pedido_id)["Sal mineral"]["id"]

        c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 5})
        c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 12})

        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Sal mineral")).first()
            assert estoque.quantidade == 12  # soma dos dois deltas (5 + 7), não 5+12
            movimentos = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.pedido_item_id == item_id)).all()
            assert sorted(m.quantidade for m in movimentos) == [5, 7]

    def test_item_servico_nao_gera_movimento_de_estoque(self, client):
        c, engine = client
        pedido_id = _criar_pedido(c, [
            {"tipo_item": "servico", "produto_servico": "Frete", "quantidade": 1, "valor_total_estimado": 100.0},
        ])
        item_id = _itens_do_pedido(c, pedido_id)["Frete"]["id"]

        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 1})
        assert r.status_code == 200
        assert r.json()["status"] == "atendido"

        with Session(engine) as s:
            movimentos = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.pedido_id == pedido_id)).all()
            assert movimentos == []


class TestPendenciasDeFechamento:
    def test_pedido_sem_lancamento_vinculado_retorna_pendencia_de_pagamento(self, client):
        c, _ = client
        pedido_id = _criar_pedido(c, [
            {"tipo_item": "produto", "produto_servico": "Sal mineral", "quantidade": 10, "valor_total_estimado": 500.0},
        ])
        item_id = _itens_do_pedido(c, pedido_id)["Sal mineral"]["id"]

        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 10})
        assert r.status_code == 200
        assert "pagamento" in r.json()["pendencias"]
        assert "data_emissao" in r.json()["pendencias"]


class TestPedidoCancelado:
    def test_pedido_cancelado_nao_aceita_marcacao_de_entrega(self, client):
        c, _ = client
        pedido_id = _criar_pedido(c, [
            {"tipo_item": "produto", "produto_servico": "Sal mineral", "quantidade": 10, "valor_total_estimado": 500.0},
        ])
        item_id = _itens_do_pedido(c, pedido_id)["Sal mineral"]["id"]

        r = c.put(f"/pedidos/{pedido_id}/status", json={"status": "cancelado"})
        assert r.status_code == 200

        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 10})
        assert r.status_code == 400

        r = c.get(f"/pedidos/{pedido_id}")
        assert r.json()["status"] == "cancelado"  # continua cancelado, sem side effect nenhum


class TestIsolamentoPorFazenda:
    def test_fazenda_2_nao_marca_entrega_em_item_da_fazenda_1(self, client):
        c, _ = client
        pedido_id = _criar_pedido(c, [
            {"tipo_item": "produto", "produto_servico": "Sal mineral", "quantidade": 10, "valor_total_estimado": 500.0},
        ])
        item_id = _itens_do_pedido(c, pedido_id)["Sal mineral"]["id"]

        _como_fazenda(2)
        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 10})
        assert r.status_code == 404

        _como_fazenda(1)
        r = c.get(f"/pedidos/{pedido_id}")
        assert r.json()["itens"][0]["quantidade_entregue"] == 0
