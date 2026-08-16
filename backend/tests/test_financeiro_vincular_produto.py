"""
PUT /financeiro/itens/{id}/vincular-produto — associa/renomeia o produto ou
serviço de UM item já lançado a um nome do catálogo (usado tanto por
"cadastrar produto novo" quanto por "associar a produto já existente" na
tela de edição, ver FormEditarLancamento). Quando o item é produto de
estoque com quantidade > 0 e ainda sem entrada, dá baixa retroativa.

Também cobre o campo `classificacao` (Configurações > Parâmetros
financeiros > Classificação, ex.: Medicamentos) em POST/PUT /financeiro/lancamentos.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, LancamentoItem, MovimentoEstoque
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
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _lancar_teatseal(c, quantidade=24.0):
    """Nota de despesa com um produto NÃO cadastrado no estoque (nome vindo
    de XML/OCR, ex.: "TEATSEAL") — mesmo caso que não dá entrada na criação."""
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "TEATSEAL", "tipo_item": "produto", "quantidade": quantidade, "valor_total": 480.0}],
        "data_emissao": "2026-08-01",
    })
    assert r.status_code == 201, r.text
    assert r.json()["avisos_estoque"], "esperava aviso de item não encontrado no estoque"
    return r.json()


class TestVincularProdutoDaEntradaRetroativa:
    def test_associar_a_item_existente_da_entrada_com_a_quantidade_da_nota(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="TEATSEAL Selante", quantidade=0, unidade="un", estocavel=True, fazenda_id=1))
            s.commit()

        resultado = _lancar_teatseal(c, quantidade=24)
        with Session(engine) as s:
            item = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == resultado["numero_lancamento"])).first()
            item_id = item.id

        r = c.put(f"/financeiro/itens/{item_id}/vincular-produto", json={"produto": "TEATSEAL Selante"})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["produto"] == "TEATSEAL Selante"
        assert corpo["avisos_estoque"] == []

        with Session(engine) as s:
            item_atualizado = s.get(LancamentoItem, item_id)
            assert item_atualizado.produto == "TEATSEAL Selante"

            estoque = s.exec(select(Estoque).where(Estoque.nome == "TEATSEAL Selante")).first()
            assert estoque.quantidade == 24

            mov = s.exec(select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo == "compra_financeiro", MovimentoEstoque.origem_id == item_id)).first()
            assert mov is not None
            assert mov.quantidade == 24
            assert mov.movimento == "Entrada de compra"

    def test_cadastrar_produto_novo_com_mesmo_nome_tambem_da_entrada(self, client):
        c, engine = client
        resultado = _lancar_teatseal(c, quantidade=10)
        with Session(engine) as s:
            item = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == resultado["numero_lancamento"])).first()
            item_id = item.id

        # Cadastra o item de estoque agora (equivalente a "cadastrar produto
        # novo" na tela de edição) e então vincula — mesmo endpoint.
        r_cad = c.post("/estoque/", json={"nome": "TEATSEAL", "unidade": "un", "estocavel": True})
        assert r_cad.status_code == 201, r_cad.text

        r = c.put(f"/financeiro/itens/{item_id}/vincular-produto", json={"produto": "TEATSEAL"})
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "TEATSEAL")).first()
            assert estoque.quantidade == 10  # não tinha saldo inicial — só a entrada retroativa

    def test_nao_duplica_entrada_se_vincular_de_novo(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Item X", quantidade=0, unidade="un", estocavel=True, fazenda_id=1))
            s.commit()
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Item bruto", "tipo_item": "produto", "quantidade": 5, "valor_total": 50.0}],
            "data_emissao": "2026-08-01",
        })
        numero_lancamento = r.json()["numero_lancamento"]
        with Session(engine) as s:
            item_id = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == numero_lancamento)).first().id

        c.put(f"/financeiro/itens/{item_id}/vincular-produto", json={"produto": "Item X"})
        r2 = c.put(f"/financeiro/itens/{item_id}/vincular-produto", json={"produto": "Item X"})
        assert r2.status_code == 200
        assert r2.json()["avisos_estoque"] == []  # já tinha dado entrada — não repete

        with Session(engine) as s:
            estoque = s.exec(select(Estoque).where(Estoque.nome == "Item X")).first()
            assert estoque.quantidade == 5  # não dobrou

    def test_item_de_servico_so_renomeia_sem_mexer_em_estoque(self, client):
        c, engine = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Serviço bruto", "tipo_item": "servico", "valor_total": 200.0}],
            "data_emissao": "2026-08-01",
        })
        numero_lancamento = r.json()["numero_lancamento"]
        with Session(engine) as s:
            item_id = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == numero_lancamento)).first().id

        r2 = c.put(f"/financeiro/itens/{item_id}/vincular-produto", json={"produto": "Manutenção de cerca"})
        assert r2.status_code == 200
        assert r2.json()["produto"] == "Manutenção de cerca"
        assert r2.json()["avisos_estoque"] == []

    def test_item_inexistente_da_404(self, client):
        c, _ = client
        r = c.put("/financeiro/itens/999999/vincular-produto", json={"produto": "X"})
        assert r.status_code == 404

    def test_nome_vazio_e_rejeitado(self, client):
        c, engine = client
        resultado = _lancar_teatseal(c)
        with Session(engine) as s:
            item_id = s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == resultado["numero_lancamento"])).first().id
        r = c.put(f"/financeiro/itens/{item_id}/vincular-produto", json={"produto": "   "})
        assert r.status_code == 400


class TestClassificacaoLancamento:
    def test_criar_classificacao_e_listar_em_opcoes(self, client):
        c, _ = client
        r = c.post("/financeiro/classificacoes", json={"nome": "Medicamentos"})
        assert r.status_code == 200, r.text
        assert r.json()["nome"] == "Medicamentos"

        opcoes = c.get("/financeiro/opcoes").json()
        assert "Medicamentos" in opcoes["classificacoes"]

    def test_lancamento_guarda_e_devolve_classificacao(self, client):
        c, _ = client
        c.post("/financeiro/classificacoes", json={"nome": "Medicamentos"})
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa", "classificacao": "Medicamentos",
            "itens": [{"produto": "Vacina X", "tipo_item": "produto", "valor_total": 100.0}],
            "data_emissao": "2026-08-01",
        })
        assert r.status_code == 201, r.text

        listagem = c.get("/financeiro/lancamentos").json()["lancamentos"]
        achado = next(x for x in listagem if x["numero_lancamento"] == r.json()["numero_lancamento"])
        assert achado["classificacao"] == "Medicamentos"

    def test_editar_lancamento_troca_classificacao(self, client):
        c, _ = client
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Vacina X", "tipo_item": "produto", "valor_total": 100.0}],
            "data_emissao": "2026-08-01",
        })
        lancamento_id = r.json()["ids"][0]
        r2 = c.put(f"/financeiro/lancamentos/{lancamento_id}", json={"classificacao": "Medicamentos"})
        assert r2.status_code == 200
        assert r2.json()["classificacao"] == "Medicamentos"

    def test_nome_duplicado_e_rejeitado(self, client):
        c, _ = client
        c.post("/financeiro/classificacoes", json={"nome": "Medicamentos"})
        r = c.post("/financeiro/classificacoes", json={"nome": "Medicamentos"})
        assert r.status_code == 409
