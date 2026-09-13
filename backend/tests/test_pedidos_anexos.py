"""
Anexos de Pedido — orçamento, ordem de serviço ou outro documento, com
validade opcional (ver PedidoAnexo, PUT /pedidos/{id}/anexos e o alerta
correspondente na Agenda em test_agenda_pedido_documento_vencendo.py).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all


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

    import fazenda.api.routers.pedidos as pedidos_mod
    _bucket: dict[str, bytes] = {}
    monkeypatch.setattr(pedidos_mod, "enviar_arquivo", lambda caminho, conteudo, *a, **k: _bucket.__setitem__(caminho, conteudo))
    monkeypatch.setattr(pedidos_mod, "baixar_arquivo", lambda caminho, *a, **k: _bucket[caminho])
    monkeypatch.setattr(pedidos_mod, "excluir_arquivo", lambda caminho, *a, **k: _bucket.pop(caminho, None))

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _criar_pedido(client, **overrides):
    dados = {
        "tipo": "compra",
        "fornecedor_cliente": "Fornecedor Teste",
        "data_pedido": "2026-08-01",
        "itens": [{"tipo_item": "produto", "produto_servico": "Ração", "valor_total_estimado": 1000.0}],
    }
    dados.update(overrides)
    return client.post("/pedidos/", json=dados).json()["id"]


def _pdf(nome="orcamento.pdf"):
    return {"file": (nome, b"%PDF-1.4 orcamento", "application/pdf")}


class TestAnexarDocumento:
    def test_anexa_orcamento_com_validade(self, client):
        pedido_id = _criar_pedido(client)
        r = client.post(f"/pedidos/{pedido_id}/anexos", files=_pdf(), data={"categoria": "Orçamento", "data_validade": "2026-08-20"})
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["categoria"] == "Orçamento"
        assert corpo["data_validade"] == "2026-08-20"
        assert corpo["nome_arquivo"] == "orcamento.pdf"

    def test_anexa_sem_validade(self, client):
        pedido_id = _criar_pedido(client)
        r = client.post(f"/pedidos/{pedido_id}/anexos", files=_pdf("os.pdf"), data={"categoria": "Ordem de serviço"})
        assert r.status_code == 201, r.text
        assert r.json()["data_validade"] is None

    def test_categoria_invalida_e_rejeitada(self, client):
        pedido_id = _criar_pedido(client)
        r = client.post(f"/pedidos/{pedido_id}/anexos", files=_pdf(), data={"categoria": "Boleto"})
        assert r.status_code == 400

    def test_pedido_inexistente_da_404(self, client):
        r = client.post("/pedidos/999999/anexos", files=_pdf(), data={"categoria": "Orçamento"})
        assert r.status_code == 404

    def test_listar_anexos_do_pedido(self, client):
        pedido_id = _criar_pedido(client)
        client.post(f"/pedidos/{pedido_id}/anexos", files=_pdf("orcamento.pdf"), data={"categoria": "Orçamento"})
        client.post(f"/pedidos/{pedido_id}/anexos", files=_pdf("outro.pdf"), data={"categoria": "Outro documento"})
        anexos = client.get(f"/pedidos/{pedido_id}/anexos").json()
        assert sorted(a["nome_arquivo"] for a in anexos) == ["orcamento.pdf", "outro.pdf"]

    def test_conteudo_anexado_pode_ser_baixado(self, client):
        pedido_id = _criar_pedido(client)
        anexo_id = client.post(f"/pedidos/{pedido_id}/anexos", files=_pdf(), data={"categoria": "Orçamento"}).json()["id"]
        r = client.get(f"/pedidos/anexos/{anexo_id}")
        assert r.status_code == 200
        assert r.content == b"%PDF-1.4 orcamento"

    def test_excluir_anexo(self, client):
        pedido_id = _criar_pedido(client)
        anexo_id = client.post(f"/pedidos/{pedido_id}/anexos", files=_pdf(), data={"categoria": "Orçamento"}).json()["id"]
        r = client.delete(f"/pedidos/anexos/{anexo_id}")
        assert r.status_code == 200
        assert client.get(f"/pedidos/{pedido_id}/anexos").json() == []
        assert client.get(f"/pedidos/anexos/{anexo_id}").status_code == 404

    def test_excluir_pedido_remove_anexos_junto(self, client):
        pedido_id = _criar_pedido(client)
        anexo_id = client.post(f"/pedidos/{pedido_id}/anexos", files=_pdf(), data={"categoria": "Orçamento"}).json()["id"]
        assert client.delete(f"/pedidos/{pedido_id}").status_code == 204
        assert client.get(f"/pedidos/anexos/{anexo_id}").status_code == 404
