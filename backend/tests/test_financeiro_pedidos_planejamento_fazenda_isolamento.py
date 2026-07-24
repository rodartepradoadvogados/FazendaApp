"""
Isolamento por fazenda em Pedidos e Planejamento (Fase 3C) — Orçamento,
Planejamento financeiro (cenários/itens) e Pedidos. Garante que duas
fazendas podem usar o mesmo número de pedido sem conflitar entre si, que
uma fazenda não vê/edita/exclui os registros da outra, e que token legado
(sem fazenda) continua vendo tudo, exatamente como antes do retrofit
multi-tenant.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Teste"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "outroadmin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _pedido_payload(**overrides) -> dict:
    payload = {
        "tipo": "compra",
        "fornecedor_cliente": "Fornecedor Teste",
        "data_pedido": "2026-07-01",
        "itens": [
            {"tipo_item": "produto", "produto_servico": "Ração", "valor_total_estimado": 1000.0},
        ],
    }
    payload.update(overrides)
    return payload


class TestIsolamentoPedidos:
    def test_duas_fazendas_podem_usar_o_mesmo_numero_pedido(self, client):
        c, _ = client
        _como_fazenda(1)
        r1 = c.post("/pedidos/", json=_pedido_payload())
        assert r1.status_code == 201, r1.text
        numero_1 = r1.json()["numero_pedido"]

        _como_fazenda(2)
        r2 = c.post("/pedidos/", json=_pedido_payload())
        assert r2.status_code == 201, r2.text
        numero_2 = r2.json()["numero_pedido"]

        # Cada fazenda numera a partir de si mesma, então ambos ficam #00001.
        assert numero_1 == numero_2

    def test_fazenda_1_nao_ve_pedido_da_fazenda_2_na_listagem(self, client):
        c, _ = client
        _como_fazenda(2)
        c.post("/pedidos/", json=_pedido_payload(observacao="Só da fazenda 2"))

        _como_fazenda(1)
        r = c.get("/pedidos/")
        assert r.status_code == 200
        observacoes = {p.get("observacao") for p in r.json()}
        assert "Só da fazenda 2" not in observacoes

    def test_fazenda_1_nao_acessa_pedido_da_fazenda_2_por_id(self, client):
        c, _ = client
        _como_fazenda(2)
        pedido_id = c.post("/pedidos/", json=_pedido_payload()).json()["id"]

        _como_fazenda(1)
        assert c.get(f"/pedidos/{pedido_id}").status_code == 404
        assert c.put(f"/pedidos/{pedido_id}", json=_pedido_payload()).status_code == 404
        assert c.put(f"/pedidos/{pedido_id}/status", json={"status": "cancelado"}).status_code == 404
        assert c.delete(f"/pedidos/{pedido_id}").status_code == 404

    def test_fazenda_2_pode_gerenciar_seu_proprio_pedido(self, client):
        c, _ = client
        _como_fazenda(2)
        pedido_id = c.post("/pedidos/", json=_pedido_payload()).json()["id"]

        assert c.get(f"/pedidos/{pedido_id}").status_code == 200
        assert c.put(f"/pedidos/{pedido_id}/status", json={"status": "cancelado"}).status_code == 200
        assert c.delete(f"/pedidos/{pedido_id}").status_code == 204

    def test_token_legado_sem_fazenda_ve_todos_os_pedidos(self, client):
        c, _ = client
        _como_fazenda(1)
        c.post("/pedidos/", json=_pedido_payload(observacao="Fazenda 1 legado"))
        _como_fazenda(2)
        c.post("/pedidos/", json=_pedido_payload(observacao="Fazenda 2 legado"))

        _como_fazenda(None)
        r = c.get("/pedidos/")
        assert r.status_code == 200
        observacoes = {p.get("observacao") for p in r.json()}
        assert "Fazenda 1 legado" in observacoes
        assert "Fazenda 2 legado" in observacoes


class TestIsolamentoOrcamento:
    def _item_payload(self, **overrides) -> dict:
        payload = {
            "ano": 2026, "mes": 7, "codigo_conta_gerencial": "9.99",
            "tipo": "despesa", "valor_orcado": 500.0,
        }
        payload.update(overrides)
        return payload

    def test_fazenda_1_nao_ve_item_de_orcamento_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        c.post("/planejamento/orcamento", json=self._item_payload(observacao="Só fazenda 2"))

        _como_fazenda(1)
        r = c.get("/planejamento/orcamento")
        assert r.status_code == 200
        observacoes = {i.get("observacao") for i in r.json()}
        assert "Só fazenda 2" not in observacoes

    def test_fazenda_1_nao_edita_nem_exclui_item_de_orcamento_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        item_id = c.post("/planejamento/orcamento", json=self._item_payload()).json()["id"]

        _como_fazenda(1)
        assert c.put(f"/planejamento/orcamento/{item_id}", json=self._item_payload()).status_code == 404
        assert c.delete(f"/planejamento/orcamento/{item_id}").status_code == 404

    def test_token_legado_ve_itens_de_orcamento_de_todas_as_fazendas(self, client):
        c, _ = client
        _como_fazenda(1)
        c.post("/planejamento/orcamento", json=self._item_payload(observacao="F1"))
        _como_fazenda(2)
        c.post("/planejamento/orcamento", json=self._item_payload(observacao="F2"))

        _como_fazenda(None)
        r = c.get("/planejamento/orcamento")
        assert r.status_code == 200
        observacoes = {i.get("observacao") for i in r.json()}
        assert "F1" in observacoes
        assert "F2" in observacoes


class TestIsolamentoPlanejamentoCenarios:
    def test_fazenda_1_nao_ve_cenario_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        c.post("/planejamento/cenarios", json={"nome": "Cenário só da fazenda 2"})

        _como_fazenda(1)
        r = c.get("/planejamento/cenarios")
        assert r.status_code == 200
        nomes = {ce["nome"] for ce in r.json()}
        assert "Cenário só da fazenda 2" not in nomes

    def test_fazenda_1_nao_acessa_cenario_nem_itens_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        cenario_id = c.post("/planejamento/cenarios", json={"nome": "Cenário fazenda 2"}).json()["id"]
        item_payload = {
            "mes_competencia": "2026-07", "codigo_conta_gerencial": "9.99",
            "tipo": "despesa", "valor_previsto": 300.0,
        }
        c.post(f"/planejamento/cenarios/{cenario_id}/itens", json=item_payload)

        _como_fazenda(1)
        assert c.get(f"/planejamento/cenarios/{cenario_id}/itens").status_code == 404
        assert c.post(f"/planejamento/cenarios/{cenario_id}/itens", json=item_payload).status_code == 404
        assert c.put(f"/planejamento/cenarios/{cenario_id}", json={"nome": "Hackeado"}).status_code == 404
        assert c.delete(f"/planejamento/cenarios/{cenario_id}").status_code == 404

    def test_token_legado_ve_cenarios_de_todas_as_fazendas(self, client):
        c, _ = client
        _como_fazenda(1)
        c.post("/planejamento/cenarios", json={"nome": "Cenário F1"})
        _como_fazenda(2)
        c.post("/planejamento/cenarios", json={"nome": "Cenário F2"})

        _como_fazenda(None)
        r = c.get("/planejamento/cenarios")
        assert r.status_code == 200
        nomes = {ce["nome"] for ce in r.json()}
        assert "Cenário F1" in nomes
        assert "Cenário F2" in nomes


class TestIsolamentoImportarParaPedido:
    def test_fazenda_1_nao_importa_item_de_orcamento_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        item_id = c.post("/planejamento/orcamento", json={
            "ano": 2026, "mes": 7, "codigo_conta_gerencial": "9.99",
            "tipo": "despesa", "valor_orcado": 800.0,
        }).json()["id"]

        _como_fazenda(1)
        r = c.post("/planejamento/importar-para-pedido", json={
            "origem_tipo": "orcamento", "origem_item_id": item_id, "tipo_pedido": "compra",
        })
        assert r.status_code == 404

    def test_fazenda_pode_importar_seu_proprio_item_de_orcamento(self, client):
        c, _ = client
        _como_fazenda(1)
        item_id = c.post("/planejamento/orcamento", json={
            "ano": 2026, "mes": 7, "codigo_conta_gerencial": "9.99",
            "tipo": "despesa", "valor_orcado": 800.0,
        }).json()["id"]

        r = c.post("/planejamento/importar-para-pedido", json={
            "origem_tipo": "orcamento", "origem_item_id": item_id, "tipo_pedido": "compra",
        })
        assert r.status_code == 201, r.text

        pedido_id = r.json()["id"]
        p = c.get(f"/pedidos/{pedido_id}").json()
        assert p["fazenda_id"] == 1
