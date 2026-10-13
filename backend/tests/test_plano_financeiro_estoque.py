"""
Plano Financeiro §1.7 — ponto único de estoque (`estoque_baixa.movimentar` /
`abrir_lote`): fazenda SEM o módulo `estoque` contratado não grava movimento,
não mexe em saldo e não avisa nada, qualquer que seja o módulo que o
disparou (Pedido, nota de despesa no Financeiro...). Com o módulo (Gold),
o comportamento de sempre.

Os 3 testes de aceite do plano:
  (a) Pedido [financeiro, pedidos]: marcar entrega de item produto grava
      `quantidade_entregue`/status e ZERO `movimento_estoque`;
  (b) nota de despesa com item produto salva e devolve `avisos_estoque == []`;
  (c) Gold segue gerando movimento (sem regressão).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, LoteEstoque, MovimentoEstoque,
)
from fazenda.models.planos import PLANOS_CATALOGO
from fazenda.rules import estoque_baixa

FAZ_FIN = 1    # [financeiro, pedidos] — sem estoque
FAZ_GOLD = 2   # Gold — com estoque

MODULOS = {
    FAZ_FIN: ["financeiro", "pedidos"],
    FAZ_GOLD: list(PLANOS_CATALOGO["gold"]["modulos"]),
}


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for fid, modulos in MODULOS.items():
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
        s.commit()
        for fid, modulos in MODULOS.items():
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for m in modulos:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=m, preco=0.0, ativo=True))
            # Item casável por nome (a fazenda só-Financeiro o tem de "herança": prova que NÃO é tocado).
            s.add(Estoque(nome="Sal mineral", quantidade=10, unidade="saca", fazenda_id=fid))
        s.commit()

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


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _criar_pedido_com_produto(c) -> tuple[int, int]:
    r = c.post("/pedidos/", json={
        "tipo": "compra", "fornecedor_cliente": "Fornecedor Teste", "data_pedido": "2026-08-01",
        "itens": [{"tipo_item": "produto", "produto_servico": "Sal mineral", "quantidade": 10, "valor_total_estimado": 500.0}],
    })
    assert r.status_code == 201, r.text
    pedido_id = r.json()["id"]
    itens = c.get(f"/pedidos/{pedido_id}").json()["itens"]
    return pedido_id, itens[0]["id"]


def _lancar_nota(c, produto: str = "Sal mineral"):
    return c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": produto, "tipo_item": "produto", "quantidade": 25, "valor_total": 500.0}],
        "data_emissao": "2026-07-31",
    })


def _movimentos(engine, fazenda_id: int) -> list[MovimentoEstoque]:
    with Session(engine) as s:
        return list(s.exec(select(MovimentoEstoque).where(MovimentoEstoque.fazenda_id == fazenda_id)).all())


def _saldo(engine, fazenda_id: int, nome: str = "Sal mineral") -> float:
    with Session(engine) as s:
        return s.exec(select(Estoque).where(Estoque.nome == nome, Estoque.fazenda_id == fazenda_id)).first().quantidade


class TestAceiteSemEstoque:
    def test_a_pedido_marca_entrega_sem_gravar_estoque(self, client):
        c, engine = client
        _como_fazenda(FAZ_FIN)
        pedido_id, item_id = _criar_pedido_com_produto(c)

        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 10})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["item"]["quantidade_entregue"] == 10
        assert corpo["status"] == "atendido"
        assert corpo["avisos_estoque"] == []

        assert _movimentos(engine, FAZ_FIN) == []
        assert _saldo(engine, FAZ_FIN) == 10   # inalterado: nenhum estoque-fantasma

    def test_a_pedido_item_nao_cadastrado_tambem_fica_em_silencio(self, client):
        c, engine = client
        _como_fazenda(FAZ_FIN)
        r = c.post("/pedidos/", json={
            "tipo": "compra", "fornecedor_cliente": "Fornecedor", "data_pedido": "2026-08-01",
            "itens": [{"tipo_item": "produto", "produto_servico": "Produto que nunca existiu", "quantidade": 3,
                       "valor_total_estimado": 30.0}],
        })
        pedido_id = r.json()["id"]
        item_id = c.get(f"/pedidos/{pedido_id}").json()["itens"][0]["id"]
        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 3})
        assert r.status_code == 200, r.text
        assert r.json()["avisos_estoque"] == []

    def test_b_nota_de_despesa_com_item_produto_salva_sem_avisos_de_estoque(self, client):
        c, engine = client
        _como_fazenda(FAZ_FIN)
        r = _lancar_nota(c)
        assert r.status_code == 201, r.text
        assert r.json()["avisos_estoque"] == []
        assert _movimentos(engine, FAZ_FIN) == []
        assert _saldo(engine, FAZ_FIN) == 10

    def test_b_nota_com_produto_que_nao_esta_no_estoque_nao_avisa(self, client):
        """Hoje (com estoque) esse caso devolve 'não está no estoque desta fazenda'; sem o módulo, nada."""
        c, engine = client
        _como_fazenda(FAZ_FIN)
        r = _lancar_nota(c, produto="Item inexistente")
        assert r.status_code == 201, r.text
        assert r.json()["avisos_estoque"] == []
        assert _movimentos(engine, FAZ_FIN) == []


class TestGoldSemRegressao:
    def test_c_pedido_gold_da_entrada_no_estoque(self, client):
        c, engine = client
        _como_fazenda(FAZ_GOLD)
        pedido_id, item_id = _criar_pedido_com_produto(c)
        r = c.put(f"/pedidos/{pedido_id}/itens/{item_id}/entrega", json={"quantidade_entregue": 10})
        assert r.status_code == 200, r.text
        movs = _movimentos(engine, FAZ_GOLD)
        assert len(movs) == 1
        assert movs[0].pedido_id == pedido_id and movs[0].movimento == "Entrada de compra" and movs[0].quantidade == 10
        assert _saldo(engine, FAZ_GOLD) == 20   # 10 + 10

    def test_c_nota_gold_da_entrada_no_estoque(self, client):
        c, engine = client
        _como_fazenda(FAZ_GOLD)
        r = _lancar_nota(c)
        assert r.status_code == 201, r.text
        assert r.json()["avisos_estoque"] == []
        movs = _movimentos(engine, FAZ_GOLD)
        assert len(movs) == 1 and movs[0].origem_tipo == "compra_financeiro" and movs[0].quantidade == 25
        assert _saldo(engine, FAZ_GOLD) == 35

    def test_c_gold_produto_fora_do_estoque_continua_avisando(self, client):
        c, engine = client
        _como_fazenda(FAZ_GOLD)
        r = _lancar_nota(c, produto="Item inexistente")
        assert r.status_code == 201, r.text
        assert r.json()["avisos_estoque"] == ['"Item inexistente" não está no estoque desta fazenda — lançamento registrado sem baixa.']


class TestPontoUnicoDireto:
    """Chamadas diretas ao ponto único (sem HTTP): vale para QUALQUER módulo chamador."""

    def test_movimentar_sem_modulo_nao_grava_nem_avisa(self, client):
        _, engine = client
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.fazenda_id == FAZ_FIN)).first()
            avisos = estoque_baixa.movimentar(
                s, item=item, quantidade=4, unidade="saca", data=date.today(), fazenda_id=FAZ_FIN,
                movimento="Aplicação", observacao="teste", sinal=-1, exigir_modulo_estoque=True,
            )
            assert avisos == []
            # Item None também fica em silêncio (antes: aviso 'não está no estoque').
            assert estoque_baixa.movimentar(
                s, item=None, quantidade=1, unidade=None, data=date.today(), fazenda_id=FAZ_FIN,
                movimento="Aplicação", observacao="teste", produto="X", exigir_modulo_estoque=True,
            ) == []
            s.commit()
        assert _movimentos(engine, FAZ_FIN) == []
        assert _saldo(engine, FAZ_FIN) == 10

    def test_outros_modulos_nao_sao_afetados_pelo_gate(self, client):
        """Sanidade/Alimentação/IATF/BST/Agenda chamam baixar/devolver/movimentar SEM a flag:
        planos como Standard/Silver (sem `estoque`) seguem gravando como sempre."""
        _, engine = client
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.fazenda_id == FAZ_FIN)).first()
            estoque_baixa.baixar(s, item=item, quantidade=2, unidade="saca", data=date.today(),
                                 fazenda_id=FAZ_FIN, observacao="t")
            estoque_baixa.devolver(s, item=item, quantidade=1, unidade="saca", data=date.today(),
                                   fazenda_id=FAZ_FIN, observacao="t")
            s.commit()
        assert len(_movimentos(engine, FAZ_FIN)) == 2
        assert _saldo(engine, FAZ_FIN) == 9

    def test_abrir_lote_sem_modulo_nao_cria_lote(self, client):
        _, engine = client
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.fazenda_id == FAZ_FIN)).first()
            lote, avisos = estoque_baixa.abrir_lote(
                s, item=item, quantidade=5, data_compra=date.today(), fazenda_id=FAZ_FIN,
                exigir_modulo_estoque=True,
            )
            assert lote is None and avisos == []
            s.commit()
            assert s.exec(select(LoteEstoque)).all() == []
        assert _movimentos(engine, FAZ_FIN) == []

    def test_abrir_lote_com_modulo_segue_igual(self, client):
        _, engine = client
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.fazenda_id == FAZ_GOLD)).first()
            lote, avisos = estoque_baixa.abrir_lote(
                s, item=item, quantidade=5, data_compra=date.today(), fazenda_id=FAZ_GOLD,
            )
            assert lote is not None and lote.quantidade_comprada == 5
            s.commit()
        assert len(_movimentos(engine, FAZ_GOLD)) == 1

    def test_fazenda_id_none_segue_o_comportamento_atual(self, client):
        """Sem recorte de fazenda (legado) o ponto único não restringe — grava como sempre."""
        _, engine = client
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.fazenda_id == FAZ_FIN)).first()
            estoque_baixa.movimentar(
                s, item=item, quantidade=3, unidade="saca", data=date.today(), fazenda_id=None,
                movimento="Aplicação", observacao="legado", sinal=-1,
            )
            s.commit()
        assert _saldo(engine, FAZ_FIN) == 7
