"""
Fase G da Farmácia CowData (01/09/2026) — lotes/frascos de compra com baixa
FIFO. Pedido do usuário: "registrar/comprar um medicamento escolhendo um
tamanho de frasco/embalagem específico com sua própria dosagem, rastrear
múltiplos lotes de tamanhos diferentes do mesmo medicamento em estoque, e —
ao aplicar — escolher explicitamente de qual frasco/lote a dose saiu, ou, se
nenhum for escolhido, baixar automaticamente do lote mais antigo primeiro
(FIFO)."

Cobre: abertura de lote (POST /estoque/{id}/lotes) mantendo o agregado
Estoque.quantidade em sincronia, listagem, consumo FIFO (dentro de um só
lote e espalhando por mais de um), escolha explícita de lote (bypass do
FIFO), devolução (edição/exclusão de aplicação em Sanidade restaurando no
MESMO lote de origem) e compatibilidade total com itens que nunca abriram
lote nenhum (comportamento idêntico ao de antes desta feature).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, LoteEstoque, MovimentoEstoque
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
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
        permissoes = "sanidade,estoque"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _criar_item(c, nome="Maxicam 2%", **extra) -> int:
    payload = {"nome": nome, "finalidade": "Medicamento", "unidade": "ml", **extra}
    r = c.post("/estoque/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestAbrirLote:
    def test_abrir_lote_soma_no_agregado_e_cria_movimento_de_compra(self, client):
        c, engine = client
        item_id = _criar_item(c)
        r = c.post(f"/estoque/{item_id}/lotes", json={
            "quantidade": 100, "data_compra": "2026-06-01", "valor_unitario": 2.5, "numero_lote": "L1",
        })
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["quantidade_comprada"] == 100
        assert corpo["quantidade_restante"] == 100
        assert corpo["numero_lote"] == "L1"

        itens = c.get("/estoque/").json()["itens"]
        item = next(i for i in itens if i["id"] == item_id)
        assert item["quantidade"] == 100

        with Session(engine) as s:
            mov = s.exec(
                select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == item_id, MovimentoEstoque.movimento == "Entrada de compra")
            ).first()
            assert mov is not None
            assert mov.lote_id == corpo["id"]
            assert mov.quantidade == 100

    def test_quantidade_zero_ou_negativa_e_rejeitada(self, client):
        c, engine = client
        item_id = _criar_item(c)
        r = c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 0, "data_compra": "2026-06-01"})
        assert r.status_code == 400

    def test_item_de_outra_fazenda_ou_inexistente_da_404(self, client):
        c, engine = client
        r = c.post("/estoque/999999/lotes", json={"quantidade": 10, "data_compra": "2026-06-01"})
        assert r.status_code == 404

    def test_listar_lotes_ordenado_por_data_compra(self, client):
        c, engine = client
        item_id = _criar_item(c)
        c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 50, "data_compra": "2026-06-15", "numero_lote": "B"})
        c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 30, "data_compra": "2026-06-01", "numero_lote": "A"})
        r = c.get(f"/estoque/{item_id}/lotes")
        assert r.status_code == 200, r.text
        nomes = [l["numero_lote"] for l in r.json()]
        assert nomes == ["A", "B"]


def _aplicar(c, item_id, quantidade, numero="9001", lote_id=None):
    item = {"produto": _nome_do_item(c, item_id), "quantidade": quantidade, "unidade": "ml"}
    if lote_id is not None:
        item["lote_id"] = lote_id
    return c.post("/sanidade/aplicacoes", json={
        "data_aplicacao": "2026-07-01", "animais": [numero], "itens": [item], "aplicado": True,
    })


class TestConsumoFifo:
    def test_baixa_consome_lote_mais_antigo_primeiro(self, client):
        """Baixa via /sanidade/aplicacoes (a tela real de "aplicar
        medicamento") sem escolher lote nenhum — precisa cair em FIFO."""
        c, engine = client
        item_id = _criar_item(c)
        lote_a = c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 50, "data_compra": "2026-06-01"}).json()
        lote_b = c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 50, "data_compra": "2026-06-15"}).json()

        r = _aplicar(c, item_id, 20)
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            a = s.get(LoteEstoque, lote_a["id"])
            b = s.get(LoteEstoque, lote_b["id"])
            assert a.quantidade_restante == 30  # 50 - 20, só o lote mais antigo foi tocado
            assert b.quantidade_restante == 50
            item = s.get(Estoque, item_id)
            assert item.quantidade == 80  # 100 - 20

            mov = s.exec(
                select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == item_id, MovimentoEstoque.movimento == "Aplicação")
            ).first()
            assert mov.lote_id == lote_a["id"]

    def test_baixa_espalha_por_dois_lotes_quando_o_mais_antigo_nao_basta(self, client):
        c, engine = client
        item_id = _criar_item(c)
        lote_a = c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 10, "data_compra": "2026-06-01"}).json()
        lote_b = c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 50, "data_compra": "2026-06-15"}).json()

        r = _aplicar(c, item_id, 15)
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            a = s.get(LoteEstoque, lote_a["id"])
            b = s.get(LoteEstoque, lote_b["id"])
            assert a.quantidade_restante == 0
            assert b.quantidade_restante == 45  # 50 - 5 (o resto que o lote A não cobriu)
            item = s.get(Estoque, item_id)
            assert item.quantidade == 45  # 60 - 15

    def test_lote_id_explicito_bypassa_fifo(self, client):
        c, engine = client
        item_id = _criar_item(c)
        lote_a = c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 50, "data_compra": "2026-06-01"}).json()
        lote_b = c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 50, "data_compra": "2026-06-15"}).json()

        payload = {
            "data_aplicacao": "2026-07-01", "animais": ["1001"],
            "itens": [{"produto": _nome_do_item(c, item_id), "quantidade": 20, "unidade": "ml", "lote_id": lote_b["id"]}],
            "aplicado": True,
        }
        r = c.post("/sanidade/aplicacoes", json=payload)
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            a = s.get(LoteEstoque, lote_a["id"])
            b = s.get(LoteEstoque, lote_b["id"])
            assert a.quantidade_restante == 50  # intocado — o pedido foi explícito pelo lote B
            assert b.quantidade_restante == 30


class TestItemSemLoteContinuaComoAntes:
    def test_baixa_em_item_sem_nenhum_lote_nao_cria_lote_nenhum(self, client):
        """Item que nunca abriu um lote continua se comportando exatamente
        como antes da Fase G — a baixa mexe só no agregado, sem
        `LoteEstoque` nenhum e `MovimentoEstoque.lote_id` sempre None."""
        c, engine = client
        item_id = _criar_item(c, quantidade=100)
        r = _aplicar(c, item_id, 10)
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.exec(select(LoteEstoque).where(LoteEstoque.estoque_id == item_id)).all() == []
            mov = s.exec(
                select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == item_id, MovimentoEstoque.movimento == "Aplicação")
            ).first()
            assert mov.lote_id is None
            item = s.get(Estoque, item_id)
            assert item.quantidade == 90


class TestDevolucaoRestauraNoLoteCerto:
    def test_excluir_aplicacao_restaura_no_mesmo_lote_que_foi_consumido(self, client):
        c, engine = client
        item_id = _criar_item(c)
        lote_a = c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 10, "data_compra": "2026-06-01"}).json()
        c.post(f"/estoque/{item_id}/lotes", json={"quantidade": 50, "data_compra": "2026-06-15"}).json()

        payload = {
            "data_aplicacao": "2026-07-01", "animais": ["2001"],
            "itens": [{"produto": _nome_do_item(c, item_id), "quantidade": 5, "unidade": "ml"}],
            "aplicado": True,
        }
        r = c.post("/sanidade/aplicacoes", json=payload)
        assert r.status_code == 200, r.text
        sanidade_id = r.json()["sanidade_ids"][0]

        with Session(engine) as s:
            assert s.get(LoteEstoque, lote_a["id"]).quantidade_restante == 5

        r_del = c.delete(f"/sanidade/aplicacoes/{sanidade_id}")
        assert r_del.status_code == 200, r_del.text

        with Session(engine) as s:
            # A exclusão devolveu exatamente no lote A (o que a baixa consumiu),
            # não no lote B (mais recente) — o rastro veio de MovimentoEstoque.lote_id.
            assert s.get(LoteEstoque, lote_a["id"]).quantidade_restante == 10
            item = s.get(Estoque, item_id)
            assert item.quantidade == 60


def _nome_do_item(c, item_id: int) -> str:
    itens = c.get("/estoque/").json()["itens"]
    return next(i["nome"] for i in itens if i["id"] == item_id)
