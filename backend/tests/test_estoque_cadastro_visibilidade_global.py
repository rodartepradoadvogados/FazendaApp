"""
Visibilidade GLOBAL das 5 listas de apoio ao item de estoque (Categoria,
Finalidade, Unidade, Unidade de embalagem, Unidade de medida de embalagem) —
viraram catálogo (fazenda_id nulo = padrão de todo mundo, cada fazenda pode
criar as suas por cima), mesmo modelo de PrincipioAtivo/Doenca (ver
test_farmacia_visibilidade.py, que esta suíte espelha).

Local de Armazenamento fica de FORA deste teste de propósito: é dado da
fazenda (texto livre já digitado em Estoque/EstoqueSemen), continua com
filtro estrito por fazenda — ver fazenda/api/routers/cadastro/estoque.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    CategoriaEstoque, ContratoFazenda, ContratoFazendaModulo, Fazenda, FinalidadeEstoque, UnidadeEmbalagemEstoque,
    UnidadeEstoque, UnidadeMedidaEmbalagemEstoque,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

ROTAS_GLOBAIS = [
    ("categorias-estoque", CategoriaEstoque),
    ("finalidades-estoque", FinalidadeEstoque),
    ("unidades-estoque", UnidadeEstoque),
    ("unidades-embalagem-estoque", UnidadeEmbalagemEstoque),
    ("unidades-medida-embalagem-estoque", UnidadeMedidaEmbalagemEstoque),
]


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()
        # Catálogo global (como o seed cria: sem fazenda_id).
        for _, model in ROTAS_GLOBAIS:
            s.add(model(nome="Global"))
        # Personalização da fazenda 1 (nasce COM fazenda_id, nunca global).
        for _, model in ROTAS_GLOBAIS:
            s.add(model(nome="Da fazenda 1", fazenda_id=1))
        # Cadastro de OUTRA fazenda — nunca pode aparecer para a fazenda 1.
        for _, model in ROTAS_GLOBAIS:
            s.add(model(nome="Da fazenda 2", fazenda_id=2))
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
        yield c

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestCatalogoGlobalMaisDaPropriaFazenda:
    @pytest.mark.parametrize("rota,_", ROTAS_GLOBAIS)
    def test_fazenda_1_ve_global_e_a_sua_mas_nao_a_de_outra(self, client, rota, _):
        c = client
        _como_fazenda(1)
        nomes = {i["nome"] for i in c.get(f"/cadastro/{rota}").json()}
        assert nomes == {"Global", "Da fazenda 1"}, rota

    @pytest.mark.parametrize("rota,_", ROTAS_GLOBAIS)
    def test_fazenda_2_ve_global_e_a_sua_mas_nao_a_de_outra(self, client, rota, _):
        c = client
        _como_fazenda(2)
        nomes = {i["nome"] for i in c.get(f"/cadastro/{rota}").json()}
        assert nomes == {"Global", "Da fazenda 2"}, rota

    @pytest.mark.parametrize("rota,_", ROTAS_GLOBAIS)
    def test_token_legado_sem_fazenda_ve_tudo(self, client, rota, _):
        c = client
        _como_fazenda(None)
        nomes = {i["nome"] for i in c.get(f"/cadastro/{rota}").json()}
        assert nomes == {"Global", "Da fazenda 1", "Da fazenda 2"}, rota


class TestCriacaoNuncaNasceGlobal:
    @pytest.mark.parametrize("rota,_", ROTAS_GLOBAIS)
    def test_item_criado_pela_fazenda_nasce_com_fazenda_id_nunca_global(self, client, rota, _):
        c = client
        _como_fazenda(1)
        r = c.post(f"/cadastro/{rota}", json={"nome": "Recém-criado pela fazenda 1"})
        assert r.status_code == 200, r.text
        # Só a fazenda 1 enxerga o item recém-criado — se tivesse nascido
        # global (fazenda_id nulo), a fazenda 2 também veria.
        _como_fazenda(2)
        nomes_fazenda_2 = {i["nome"] for i in c.get(f"/cadastro/{rota}").json()}
        assert "Recém-criado pela fazenda 1" not in nomes_fazenda_2, rota
