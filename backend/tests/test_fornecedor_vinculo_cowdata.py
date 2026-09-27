"""
Cadastro > Estoque > Fornecedores — vínculo manual com o catálogo de
Fornecedores-padrão do Painel CowData (`Fornecedor.fornecedor_cowdata_id`).

Pedido do dono (set/2026): além do fan-out automático (que casa por nome
exato — ver test_painel_cowdata_cotacoes.py::TestFanOutFornecedorParaFazendas),
a fazenda precisa poder VINCULAR manualmente um fornecedor que ela mesma já
tinha cadastrado (nome diferente do catálogo CowData) a um dos
fornecedores-padrão, evitando duplicata.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Fornecedor, FornecedorCowData


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

    with Session(engine) as s:
        s.add(FornecedorCowData(id=1, nome="Vallée S.A.", ativo=True))
        s.add(FornecedorCowData(id=2, nome="Fornecedor Desativado no Catálogo", ativo=False))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestListaFornecedoresPadraoParaVinculo:
    def test_lista_so_id_e_nome_dos_ativos(self, client):
        c, _ = client
        r = c.get("/cadastro/fornecedores-padrao")
        assert r.status_code == 200
        assert r.json() == [{"id": 1, "nome": "Vallée S.A."}]  # o desativado (id=2) não aparece


class TestVincularFornecedorProprioAoPadraoCowData:
    def test_criar_fornecedor_com_vinculo(self, client):
        c, _ = client
        r = c.post("/cadastro/fornecedores", json={
            "nome": "Vallee (digitado sem acento)", "tipo": "fornecedor", "fornecedor_cowdata_id": 1,
        })
        assert r.status_code == 200, r.text
        assert r.json()["fornecedor_cowdata_id"] == 1

    def test_editar_fornecedor_ja_existente_para_vincular_depois(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Fornecedor(id=10, fazenda_id=None, nome="Vallee (nome antigo)", tipo="fornecedor"))
            s.commit()
        r = c.put("/cadastro/fornecedores/10", json={"nome": "Vallee (nome antigo)", "tipo": "fornecedor", "fornecedor_cowdata_id": 1})
        assert r.status_code == 200, r.text
        assert r.json()["fornecedor_cowdata_id"] == 1

    def test_vinculo_e_opcional(self, client):
        c, _ = client
        r = c.post("/cadastro/fornecedores", json={"nome": "Fornecedor Qualquer", "tipo": "fornecedor"})
        assert r.status_code == 200
        assert r.json()["fornecedor_cowdata_id"] is None
