"""
Embalagens de um item de Estoque (04/09/2026) — pedido do usuário: "eu quero
comprar um Agrovet de 50ml e um Agrovet de 100ml, não preciso ter que
cadastrar 2 produtos". Cobre: cadastro/remoção de tamanhos
(ApresentacaoEmbalagemEstoque), compra por embalagem abrindo um lote com o
total já convertido (nº de frascos × tamanho), a mesma compra feita via
Financeiro, e o guard que recusa corrigir automaticamente a quantidade de um
item comprado por embalagem (a correção ingênua multiplicaria/dividiria
errado, exatamente o risco de unidade que o usuário pediu pra evitar).
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
        permissoes = "sanidade,estoque,financeiro"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _criar_item(c, nome="Agrovet", **extra) -> int:
    payload = {"nome": nome, "finalidade": "Medicamento", "unidade": "ml", "medida_embalagem": "ml/frasco", **extra}
    r = c.post("/estoque/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestEmbalagens:
    def test_cadastrar_listar_remover_embalagem(self, client):
        c, engine = client
        item_id = _criar_item(c)

        r = c.post(f"/estoque/{item_id}/embalagens", json={"quantidade": 50})
        assert r.status_code == 201, r.text
        emb_50 = r.json()
        assert emb_50["quantidade"] == 50
        assert emb_50["ativa"] is True

        r = c.post(f"/estoque/{item_id}/embalagens", json={"quantidade": 100})
        assert r.status_code == 201, r.text
        emb_100 = r.json()

        lista = c.get(f"/estoque/{item_id}/embalagens").json()
        assert {e["quantidade"] for e in lista} == {50, 100}

        r = c.delete(f"/estoque/{item_id}/embalagens/{emb_50['id']}")
        assert r.status_code == 200
        lista2 = c.get(f"/estoque/{item_id}/embalagens").json()
        ativa_50 = next(e for e in lista2 if e["id"] == emb_50["id"])
        assert ativa_50["ativa"] is False

    def test_quantidade_invalida_e_rejeitada(self, client):
        c, engine = client
        item_id = _criar_item(c)
        r = c.post(f"/estoque/{item_id}/embalagens", json={"quantidade": 0})
        assert r.status_code == 400


class TestCompraPorEmbalagem:
    def test_abrir_lote_com_apresentacao_converte_frascos_para_total(self, client):
        c, engine = client
        item_id = _criar_item(c)
        emb = c.post(f"/estoque/{item_id}/embalagens", json={"quantidade": 100}).json()

        r = c.post(f"/estoque/{item_id}/lotes", json={
            "quantidade": 6, "data_compra": "2026-09-04", "apresentacao_id": emb["id"],
        })
        assert r.status_code == 201, r.text
        corpo = r.json()
        # 6 frascos de 100ml = 600ml, não 6 (o número de embalagens digitado).
        assert corpo["quantidade_comprada"] == 600
        assert corpo["apresentacao_id"] == emb["id"]

        itens = c.get("/estoque/").json()["itens"]
        item = next(i for i in itens if i["id"] == item_id)
        assert item["quantidade"] == 600

        lotes = c.get(f"/estoque/{item_id}/lotes").json()
        assert lotes[0]["apresentacao_quantidade"] == 100

    def test_apresentacao_de_outro_item_e_rejeitada(self, client):
        c, engine = client
        item_a = _criar_item(c, nome="Agrovet")
        item_b = _criar_item(c, nome="Sincrogest")
        emb_de_b = c.post(f"/estoque/{item_b}/embalagens", json={"quantidade": 10}).json()

        r = c.post(f"/estoque/{item_a}/lotes", json={
            "quantidade": 2, "data_compra": "2026-09-04", "apresentacao_id": emb_de_b["id"],
        })
        assert r.status_code == 404


class TestCompraPorEmbalagemViaFinanceiro:
    def _lancar(self, c, **overrides):
        payload = {
            "tipo": "despesa",
            "itens": [{"produto": "Agrovet", "tipo_item": "produto", "quantidade": 6, "valor_total": 300.0}],
            "data_emissao": "2026-09-04",
        }
        payload.update(overrides)
        return c.post("/financeiro/lancamentos", json=payload)

    def test_compra_com_apresentacao_abre_lote_rastreavel(self, client):
        c, engine = client
        item_id = _criar_item(c)
        emb = c.post(f"/estoque/{item_id}/embalagens", json={"quantidade": 100}).json()

        r = self._lancar(c, itens=[{
            "produto": "Agrovet", "tipo_item": "produto", "quantidade": 6, "valor_total": 300.0,
            "apresentacao_id": emb["id"],
        }])
        assert r.status_code == 201, r.text
        item_criado_id = r.json()["ids"][0]

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.id == item_id)).first()
            assert item.quantidade == 600  # 6 frascos x 100ml, não 6

            lote = s.exec(select(LoteEstoque).where(LoteEstoque.estoque_id == item_id)).first()
            assert lote is not None
            assert lote.apresentacao_id == emb["id"]
            assert lote.quantidade_comprada == 600

            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == item_id)).first()
            assert mov.lote_id == lote.id
            # origem_tipo/origem_id precisam ficar gravados — sem isso, editar
            # a quantidade deste item depois não encontraria o que corrigir.
            assert mov.origem_tipo == "compra_financeiro"

        # Recusa (não corrige errado) a edição de quantidade de um item
        # comprado por embalagem — ver comentário em editar_lancamento.
        r_editar = c.put(f"/financeiro/lancamentos/{item_criado_id}", json={"quantidade": 12})
        assert r_editar.status_code == 400
        assert "embalagem" in r_editar.json()["detail"].lower()
