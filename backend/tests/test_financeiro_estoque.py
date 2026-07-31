"""
Compra de produto estocável no Financeiro dá entrada automática no estoque
(POST /financeiro/lancamentos, despesa, item tipo_item="produto", sem
pedido_id — ver fazenda/api/routers/financeiro.py:criar_lancamento).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, MovimentoEstoque
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

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

    with Session(engine) as s:
        # exigir_modulo_contratado("financeiro") (main.py) exige contrato
        # ativo + módulo "financeiro" contratado por fazenda_id — sem isso
        # toda chamada com get_fazenda_atual_id != None cai em 403.
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.add(Estoque(nome="Ração concentrada", quantidade=10, unidade="kg", fazenda_id=1))
        s.add(Estoque(nome="Ração concentrada", quantidade=100, unidade="kg", fazenda_id=2))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _lancar(c, **overrides):
    payload = {
        "tipo": "despesa",
        "itens": [{"produto": "Ração concentrada", "tipo_item": "produto", "quantidade": 25, "valor_total": 500.0}],
        "data_emissao": "2026-07-31",
    }
    payload.update(overrides)
    return c.post("/financeiro/lancamentos", json=payload)


class TestEntradaAutomaticaCompra:
    def test_despesa_produto_estocavel_da_entrada(self, client):
        c, engine = client
        r = _lancar(c)
        assert r.status_code == 201
        assert r.json()["avisos_estoque"] == []

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração concentrada", Estoque.fazenda_id == 1)).first()
            assert item.quantidade == 35  # 10 + 25

            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "compra_financeiro")).first()
            assert mov is not None
            assert mov.movimento == "Entrada de compra"
            assert mov.quantidade == 25
            assert mov.fazenda_id == 1
            assert mov.estoque_id == item.id

    def test_produto_nao_cadastrado_no_estoque_nao_da_erro_nem_entrada(self, client):
        c, engine = client
        r = _lancar(c, itens=[{"produto": "Item inexistente", "tipo_item": "produto", "quantidade": 5, "valor_total": 100.0}])
        assert r.status_code == 201
        assert r.json()["avisos_estoque"] == []
        with Session(engine) as s:
            assert s.exec(select(MovimentoEstoque)).first() is None

    def test_item_servico_nunca_mexe_no_estoque(self, client):
        c, engine = client
        r = _lancar(c, itens=[{"produto": "Ração concentrada", "tipo_item": "servico", "quantidade": 25, "valor_total": 500.0}])
        assert r.status_code == 201
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração concentrada", Estoque.fazenda_id == 1)).first()
            assert item.quantidade == 10  # inalterado
            assert s.exec(select(MovimentoEstoque)).first() is None

    def test_com_pedido_id_nao_da_entrada_automatica(self, client):
        c, engine = client
        r = _lancar(c, pedido_id=999)
        assert r.status_code == 201
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração concentrada", Estoque.fazenda_id == 1)).first()
            assert item.quantidade == 10  # inalterado — entrada é manual via /estoque/movimentar
            assert s.exec(select(MovimentoEstoque)).first() is None

    def test_receita_nunca_mexe_no_estoque(self, client):
        c, engine = client
        r = _lancar(c, tipo="receita")
        assert r.status_code == 201
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração concentrada", Estoque.fazenda_id == 1)).first()
            assert item.quantidade == 10
            assert s.exec(select(MovimentoEstoque)).first() is None

    def test_isolamento_produto_mesmo_nome_outra_fazenda_nao_e_afetado(self, client):
        c, engine = client
        r = _lancar(c)
        assert r.status_code == 201
        with Session(engine) as s:
            item_fazenda_2 = s.exec(select(Estoque).where(Estoque.nome == "Ração concentrada", Estoque.fazenda_id == 2)).first()
            assert item_fazenda_2.quantidade == 100  # inalterado
