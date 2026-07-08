"""
Testes do router de exclusões: prévia de impacto e exclusão em cascata.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ContaGerencial, ControleLeiteiro, Parto, Sanidade, Servico


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    # Admin fake: sobrescreve as dependências de autenticação usadas pelo router.
    from fazenda.auth import exigir_admin, get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    main.app.dependency_overrides[exigir_admin] = lambda: _FakeAdmin()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _sessao(engine) -> Session:
    return Session(engine)


class TestExclusaoAnimal:
    def test_impacto_lista_registros_relacionados(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Animal(numero="123", ativo=True))
            s.add(Servico(numero_matriz="123", data_servico=date(2026, 1, 1)))
            s.add(Parto(numero_matriz="123", data_parto=date(2026, 2, 1)))
            s.add(ControleLeiteiro(numero_matriz="123", data_controle=date(2026, 3, 1)))
            s.add(Sanidade(numero_matriz="123", produto="Vacina X", data_aplicacao=date(2026, 1, 5)))
            s.commit()

        r = c.post("/exclusoes/impacto", json={"tipo": "animal", "id": "123"})
        assert r.status_code == 200
        impacto = r.json()["impacto"]
        assert any("Ficha do animal 123" in i for i in impacto)
        assert any("1 serviço" in i for i in impacto)
        assert any("1 parto" in i for i in impacto)
        assert any("1 registro" in i for i in impacto)
        assert any("1 aplicação" in i for i in impacto)

    def test_confirmar_apaga_animal_e_relacionados(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Animal(numero="999", ativo=True))
            s.add(Servico(numero_matriz="999", data_servico=date(2026, 1, 1)))
            s.commit()

        r = c.post("/exclusoes/confirmar", json={"tipo": "animal", "id": "999"})
        assert r.status_code == 200
        assert r.json()["excluido"] is True

        with _sessao(engine) as s:
            from sqlmodel import select
            assert s.exec(select(Animal).where(Animal.numero == "999")).first() is None
            assert s.exec(select(Servico).where(Servico.numero_matriz == "999")).first() is None

    def test_animal_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/exclusoes/impacto", json={"tipo": "animal", "id": "nope"})
        assert r.status_code == 404


class TestExclusaoFinanceiro:
    def test_impacto_de_parcela_lista_todas_as_irmas(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(numero_lancamento="LC-2026-00001", parcela_num=1, parcela_total=2, valor_total=100, descricao="Sal mineral"))
            s.add(ContaGerencial(numero_lancamento="LC-2026-00001", parcela_num=2, parcela_total=2, valor_total=100, descricao="Sal mineral"))
            s.commit()
            ids = [row.id for row in s.exec(__import__("sqlmodel").select(ContaGerencial)).all()]

        r = c.post("/exclusoes/impacto", json={"tipo": "financeiro", "id": str(ids[0])})
        assert r.status_code == 200
        impacto = r.json()["impacto"]
        assert any("2 parcela" in i for i in impacto)

    def test_confirmar_apaga_todas_as_parcelas(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(numero_lancamento="LC-2026-00002", parcela_num=1, parcela_total=2, valor_total=50))
            s.add(ContaGerencial(numero_lancamento="LC-2026-00002", parcela_num=2, parcela_total=2, valor_total=50))
            s.commit()
            ids = [row.id for row in s.exec(__import__("sqlmodel").select(ContaGerencial)).all()]

        r = c.post("/exclusoes/confirmar", json={"tipo": "financeiro", "id": str(ids[0])})
        assert r.status_code == 200

        with _sessao(engine) as s:
            from sqlmodel import select
            restantes = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == "LC-2026-00002")).all()
            assert restantes == []

    def test_confirmar_lancamento_sem_parcela_apaga_so_ele(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(ContaGerencial(numero_lancamento="LC-2026-00003", parcela_num=1, parcela_total=1, valor_total=300))
            s.commit()
            id_ = s.exec(__import__("sqlmodel").select(ContaGerencial)).first().id

        r = c.post("/exclusoes/confirmar", json={"tipo": "financeiro", "id": str(id_)})
        assert r.status_code == 200
        assert r.json()["excluido"] is True


class TestBusca:
    def test_buscar_animal_filtra_por_termo(self, client):
        c, engine = client
        with _sessao(engine) as s:
            s.add(Animal(numero="111", ativo=True))
            s.add(Animal(numero="222", ativo=True))
            s.commit()

        r = c.get("/exclusoes/buscar", params={"tipo": "animal", "termo": "111"})
        assert r.status_code == 200
        resultados = r.json()
        assert len(resultados) == 1
        assert resultados[0]["id"] == "111"

    def test_tipo_invalido_da_400(self, client):
        c, _ = client
        r = c.get("/exclusoes/buscar", params={"tipo": "invalido"})
        assert r.status_code == 400
