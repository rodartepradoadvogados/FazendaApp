"""
Testes de lançamento de entrada/saída de estoque — dá baixa ou soma direto
na quantidade do item.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, EstoqueSemen, SeedFlag


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
            s.add(Estoque(nome="Borgal 50ml", quantidade=10, estoque_minimo=5, unidade="unidade"))
            s.add(Estoque(nome="Frete de touro", quantidade=0, unidade="unidade", estocavel=False))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestMovimentarEstoque:
    def test_saida_da_baixa(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Aplicação", "quantidade": 3,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 200
        assert r.json()["quantidade"] == 7

    def test_entrada_soma(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Entrada de ajuste", "quantidade": 5,
            "data_movimento": "2026-07-08",
        })
        assert r.json()["quantidade"] == 15

    def test_marca_abaixo_minimo(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Saída de ajuste", "quantidade": 8,
            "data_movimento": "2026-07-08",
        })
        assert r.json()["quantidade"] == 2
        assert r.json()["abaixo_minimo"] is True

    def test_item_inexistente_da_404(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Não existe", "movimento": "Aplicação", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 404

    def test_movimento_invalido_da_400(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Sei lá", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 400

    def test_registra_historico(self, client):
        client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Aplicação", "quantidade": 3,
            "data_movimento": "2026-07-08", "observacao": "teste",
        })
        r = client.get("/estoque/movimentos")
        assert r.json()["total"] == 1
        assert r.json()["movimentos"][0]["nome_item"] == "Borgal 50ml"


class TestCriarItemEstoque:
    def test_cria_item_com_campos_completos(self, client):
        r = client.post("/estoque/", json={
            "nome": "Sal mineral", "categoria": "Alimento", "unidade": "saca 30kg",
            "quantidade": 10, "estoque_minimo": 5, "valor_unitario": 80.0,
            "carencia_dias": 0, "centro_custo_padrao": "Pecuária",
            "conta_gerencial_despesa_padrao": "3.01.01.03",
            "exibir_necessidade_compra_agenda": True,
        })
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["nome"] == "Sal mineral"
        assert corpo["valor_total"] == 800.0
        assert corpo["ativo"] is True
        assert corpo["exibir_necessidade_compra_agenda"] is True
        assert corpo["conta_gerencial_despesa_padrao"] == "3.01.01.03"

    def test_nome_duplicado_da_409(self, client):
        r = client.post("/estoque/", json={"nome": "Borgal 50ml"})
        assert r.status_code == 409

    def test_finalidade_persiste_no_cadastro(self, client):
        r = client.post("/estoque/", json={"nome": "Ração Milho 2", "finalidade": "Ração/Alimento", "quantidade": 100})
        assert r.status_code == 201
        assert r.json()["finalidade"] == "Ração/Alimento"

    def test_marca_abaixo_minimo_na_criacao(self, client):
        r = client.post("/estoque/", json={"nome": "Concentrado", "quantidade": 2, "estoque_minimo": 10})
        assert r.json()["abaixo_minimo"] is True

    def test_estocavel_default_true(self, client):
        r = client.post("/estoque/", json={"nome": "Concentrado2", "quantidade": 2})
        assert r.json()["estocavel"] is True

    def test_cria_item_nao_estocavel(self, client):
        r = client.post("/estoque/", json={"nome": "Serviço de frete", "estocavel": False})
        assert r.json()["estocavel"] is False

    def test_listagem_em_ordem_alfabetica(self, client):
        for nome in ["Zinco", "Amoxicilina", "Mastite Injetável"]:
            client.post("/estoque/", json={"nome": nome})
        nomes = [i["nome"] for i in client.get("/estoque/").json()["itens"]]
        meus = [n for n in nomes if n in ("Zinco", "Amoxicilina", "Mastite Injetável")]
        assert meus == ["Amoxicilina", "Mastite Injetável", "Zinco"]


class TestEstocavel:
    def test_doacao_rejeitada_para_item_nao_estocavel(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Frete de touro", "movimento": "Doação", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 400

    def test_entrada_cortesia_rejeitada_para_item_nao_estocavel(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Frete de touro", "movimento": "Entrada de cortesia", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 400

    def test_ajuste_normal_permitido_para_item_nao_estocavel(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Frete de touro", "movimento": "Entrada de ajuste", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 200

    def test_doacao_permitida_para_item_estocavel(self, client):
        r = client.post("/estoque/movimentar", json={
            "nome": "Borgal 50ml", "movimento": "Doação", "quantidade": 1,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 200


class TestSincroniaEstoqueSemen:
    """Item de Estoque genérico vinculado a um touro do Estoque de Sêmen
    (Estoque.estoque_semen_id) — entrada/saída deste item passa a atualizar
    as doses do touro também (ver `_criar_movimento_estoque`)."""

    def _doses(self, client, touro_nome: str) -> int:
        item = next(t for t in client.get("/cadastro/estoque-semen").json() if t["touro_nome"] == touro_nome)
        return item["doses"]

    def test_movimento_de_item_vinculado_atualiza_doses_do_touro(self, client):
        touro_id = client.post("/cadastro/estoque-semen", json={"touro_nome": "Hagen", "tipo": "sexado", "doses": 10}).json()["id"]
        item_id = client.post("/estoque/", json={"nome": "Sêmen Hagen", "quantidade": 0}).json()["id"]
        r = client.put(f"/cadastro/estoque-itens/{item_id}", json={"estoque_semen_id": touro_id})
        assert r.status_code == 200
        assert r.json()["estoque_semen_id"] == touro_id

        r = client.post("/estoque/movimentar", json={
            "nome": "Sêmen Hagen", "movimento": "Entrada de ajuste", "quantidade": 5,
            "data_movimento": "2026-07-08",
        })
        assert r.status_code == 200
        assert self._doses(client, "Hagen") == 15

        r = client.post("/estoque/movimentar", json={
            "nome": "Sêmen Hagen", "movimento": "Saída de ajuste", "quantidade": 4,
            "data_movimento": "2026-07-09",
        })
        assert r.status_code == 200
        assert self._doses(client, "Hagen") == 11

    def test_criacao_de_item_casa_automaticamente_pelo_nome_do_touro(self, client):
        touro_id = client.post("/cadastro/estoque-semen", json={"touro_nome": "Coors", "tipo": "convencional", "doses": 20}).json()["id"]
        r = client.post("/estoque/", json={"nome": "Coors", "quantidade": 0})
        assert r.status_code == 201
        assert r.json()["estoque_semen_id"] == touro_id

    def test_criacao_de_item_casa_pelo_naab_contido_no_nome(self, client):
        touro_id = client.post("/cadastro/estoque-semen", json={"touro_nome": "Frederico", "naab": "7HO12345", "tipo": "fazenda", "doses": 0}).json()["id"]
        r = client.post("/estoque/", json={"nome": "Sêmen 7HO12345", "quantidade": 0})
        assert r.status_code == 201
        assert r.json()["estoque_semen_id"] == touro_id

    def test_nao_casa_quando_nao_ha_touro_correspondente(self, client):
        r = client.post("/estoque/", json={"nome": "Sal mineral 2", "quantidade": 0})
        assert r.status_code == 201
        assert r.json()["estoque_semen_id"] is None


@pytest.fixture
def client_engine():
    """Variante do fixture `client` que também expõe o `engine` — usada só
    pelos testes de `sindicar_estoque_semen`, que precisam chamar a função
    diretamente contra uma sessão (e apagar a SeedFlag entre chamadas)."""
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
        yield c, engine

    main.app.dependency_overrides.clear()


class TestSindicanciaEstoqueSemen:
    _CHAVE = "estoque_vinculo_semen_202607"

    def _limpar_marca(self, session):
        # A lifespan da app já roda a sindicância (SeedFlag) com o banco vazio
        # ao subir o TestClient — remove a marca para poder testar de novo com
        # os itens inseridos pelo teste.
        flag = session.get(SeedFlag, self._CHAVE)
        if flag:
            session.delete(flag)
            session.commit()

    def test_vincula_por_nome_e_nunca_sobrescreve_manual(self, client_engine):
        c, engine = client_engine
        from fazenda.api.routers.estoque import sindicar_estoque_semen

        with Session(engine) as s:
            self._limpar_marca(s)
            s.add(EstoqueSemen(touro_nome="Semex Titan", tipo="convencional", doses=8))
            outro_touro = EstoqueSemen(touro_nome="Outro Touro", tipo="convencional", doses=1)
            s.add(outro_touro)
            s.add(Estoque(nome="Semex Titan", quantidade=0))
            s.commit()
            s.refresh(outro_touro)
            outro_touro_id = outro_touro.id
            # Item cujo NOME casaria com "Semex Titan", mas já foi vinculado
            # manualmente a um touro diferente — a sindicância não deve mexer.
            s.add(Estoque(nome="Semex Titan (comprado avulso)", quantidade=0, estoque_semen_id=outro_touro_id))
            s.commit()

        with Session(engine) as s:
            sindicar_estoque_semen(s)

        with Session(engine) as s:
            semex = s.exec(select(Estoque).where(Estoque.nome == "Semex Titan")).first()
            assert semex.estoque_semen_id is not None
            manual = s.exec(select(Estoque).where(Estoque.nome == "Semex Titan (comprado avulso)")).first()
            assert manual.estoque_semen_id == outro_touro_id

    def test_roda_uma_unica_vez(self, client_engine):
        c, engine = client_engine
        from fazenda.api.routers.estoque import sindicar_estoque_semen

        with Session(engine) as s:
            self._limpar_marca(s)
            s.add(EstoqueSemen(touro_nome="Semex Titan", tipo="convencional", doses=8))
            s.add(Estoque(nome="Semex Titan", quantidade=0))
            s.commit()

        with Session(engine) as s:
            sindicar_estoque_semen(s)
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Semex Titan")).first()
            item.estoque_semen_id = None  # simula um ajuste manual, "desvinculando"
            s.add(item)
            s.commit()

        with Session(engine) as s:
            sindicar_estoque_semen(s)  # já rodou uma vez — não deve rodar de novo

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Semex Titan")).first()
            assert item.estoque_semen_id is None
