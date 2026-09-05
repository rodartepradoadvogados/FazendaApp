"""
Cadastros de apoio ao item de estoque (Configurações > Cadastro > Estoque):
Local de Armazenamento, Categoria, Finalidade, Unidade, Unidade (embalagem) e
Unidade de Medida — ver fazenda/api/routers/cadastro/estoque.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.api.routers.cadastro import seed_cadastros_estoque
from fazenda.models import Estoque, EstoqueSemen


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

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


ENDPOINTS = [
    ("locais-armazenamento", None),
    ("categorias-estoque", 9),
    ("finalidades-estoque", 5),
    ("unidades-estoque", 8),
    ("unidades-embalagem-estoque", 8),
    ("unidades-medida-embalagem-estoque", 6),
]


class TestSeedIdempotente:
    def test_seed_cria_listas_padrao(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_cadastros_estoque(s)
        for rota, esperado in ENDPOINTS:
            if esperado is None:
                continue
            r = c.get(f"/cadastro/{rota}")
            assert r.status_code == 200
            assert len(r.json()) == esperado, rota

    def test_seed_nao_duplica_ao_rodar_de_novo(self, client):
        c, engine = client
        with Session(engine) as s:
            seed_cadastros_estoque(s)
            seed_cadastros_estoque(s)
        r = c.get("/cadastro/categorias-estoque")
        assert len(r.json()) == 9

    def test_seed_local_armazenamento_a_partir_de_dados_existentes(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Borgal", local_armazenamento="Farmácia 1"))
            s.add(Estoque(nome="Ivomec", local_armazenamento="Farmácia 1"))
            s.add(Estoque(nome="Ração", local_armazenamento="Depósito"))
            s.add(EstoqueSemen(touro_nome="Touro X", local_armazenamento="Botijão 1"))
            s.commit()
            seed_cadastros_estoque(s)
        r = c.get("/cadastro/locais-armazenamento")
        nomes = {i["nome"] for i in r.json()}
        assert nomes == {"Farmácia 1", "Depósito", "Botijão 1"}


class TestLocalArmazenamentoEDadoDaFazendaNuncaCatalogo:
    """Local de Armazenamento NÃO virou catálogo global (ao contrário das
    outras 5 listas, ver test_estoque_cadastro_visibilidade_global.py) — é
    texto livre já digitado em Estoque/EstoqueSemen, então nasce com o MESMO
    fazenda_id do item de origem, nunca nulo/global."""

    @staticmethod
    def _com_contrato_ativo(s, fazenda_id: int) -> None:
        from fazenda.models import ContratoFazenda, ContratoFazendaModulo
        from fazenda.models.planos import MODULOS_COMERCIAIS
        s.add(ContratoFazenda(fazenda_id=fazenda_id, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=fazenda_id, modulo=modulo, preco=0.0, ativo=True))

    def test_local_de_uma_fazenda_nao_vaza_pra_outra(self, client):
        c, engine = client
        from fazenda.models import Fazenda
        with Session(engine) as s:
            s.add(Fazenda(id=1, nome="Fazenda 1"))
            s.add(Fazenda(id=2, nome="Fazenda 2"))
            self._com_contrato_ativo(s, 1)
            self._com_contrato_ativo(s, 2)
            s.add(Estoque(nome="Borgal", local_armazenamento="Farmácia 1", fazenda_id=1))
            s.add(Estoque(nome="Ração", local_armazenamento="Depósito 2", fazenda_id=2))
            s.commit()
            seed_cadastros_estoque(s)

        import main
        from fazenda.auth import get_fazenda_atual_id

        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        nomes_f1 = {i["nome"] for i in c.get("/cadastro/locais-armazenamento").json()}
        assert nomes_f1 == {"Farmácia 1"}

        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 2
        nomes_f2 = {i["nome"] for i in c.get("/cadastro/locais-armazenamento").json()}
        assert nomes_f2 == {"Depósito 2"}

    def test_mesmo_nome_em_fazendas_diferentes_nao_duplica_ao_rodar_de_novo(self, client):
        c, engine = client
        from fazenda.models import Fazenda
        with Session(engine) as s:
            s.add(Fazenda(id=1, nome="Fazenda 1"))
            s.add(Fazenda(id=2, nome="Fazenda 2"))
            s.add(Estoque(nome="Borgal", local_armazenamento="Almoxarifado", fazenda_id=1))
            s.add(Estoque(nome="Ração", local_armazenamento="Almoxarifado", fazenda_id=2))
            s.commit()
            seed_cadastros_estoque(s)
            seed_cadastros_estoque(s)

            from fazenda.models import LocalArmazenamento
            from sqlmodel import select
            locais = s.exec(select(LocalArmazenamento).where(LocalArmazenamento.nome == "Almoxarifado")).all()
            assert {l.fazenda_id for l in locais} == {1, 2}
            assert len(locais) == 2, "não deveria duplicar ao rodar o seed de novo"


class TestCrudGenerico:
    @pytest.mark.parametrize("rota", [e[0] for e in ENDPOINTS])
    def test_cria_edita_e_lista(self, client, rota):
        c, _ = client
        r = c.post(f"/cadastro/{rota}", json={"nome": "Item de teste"})
        assert r.status_code == 200
        item_id = r.json()["id"]
        assert r.json()["ativo"] is True

        r = c.put(f"/cadastro/{rota}/{item_id}", json={"nome": "Item renomeado", "ativo": False})
        assert r.status_code == 200
        assert r.json()["nome"] == "Item renomeado"
        assert r.json()["ativo"] is False

        itens = c.get(f"/cadastro/{rota}").json()
        assert any(i["id"] == item_id and i["nome"] == "Item renomeado" for i in itens)

    def test_sem_nome_da_erro(self, client):
        c, _ = client
        r = c.post("/cadastro/locais-armazenamento", json={"nome": "   "})
        assert r.status_code == 400

    def test_nome_duplicado_da_erro(self, client):
        c, _ = client
        c.post("/cadastro/locais-armazenamento", json={"nome": "Depósito"})
        r = c.post("/cadastro/locais-armazenamento", json={"nome": "Depósito"})
        assert r.status_code == 409

    def test_editar_inexistente_404(self, client):
        c, _ = client
        r = c.put("/cadastro/locais-armazenamento/9999", json={"nome": "X"})
        assert r.status_code == 404

    @pytest.mark.parametrize("rota", [e[0] for e in ENDPOINTS])
    def test_excluir_remove_de_fato(self, client, rota):
        c, _ = client
        item_id = c.post(f"/cadastro/{rota}", json={"nome": "Item para excluir"}).json()["id"]

        r = c.delete(f"/cadastro/{rota}/{item_id}")
        assert r.status_code == 200, r.text
        assert r.json() == {"excluido": True}

        itens = c.get(f"/cadastro/{rota}").json()
        assert not any(i["id"] == item_id for i in itens)

    def test_excluir_inexistente_404(self, client):
        c, _ = client
        r = c.delete("/cadastro/locais-armazenamento/9999")
        assert r.status_code == 404
