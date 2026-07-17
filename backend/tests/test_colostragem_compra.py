"""
Agenda: lembrete de colostragem + IgG 24h após o parto (bezerra sem dados).
Compra de animal: vincula o valor à ficha do animal.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ColostragemBezerra, Parto


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
        permissoes = "reproducao,sanidade,financeiro"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestAgendaColostragemIgg:
    def _parto(self, engine, data_parto: date):
        with Session(engine) as s:
            s.add(Animal(numero="2074", sexo="F", ativo=True))
            # Bezerra recém-nascida, filha da 2074.
            s.add(Animal(numero="486", sexo="F", ativo=True, data_nasc=data_parto, mae_numero="2074"))
            s.add(Parto(numero_matriz="2074", data_parto=data_parto))
            s.commit()

    def test_colostragem_e_igg_entram_no_dia_seguinte(self, client):
        c, engine = client
        hoje = date.today()
        self._parto(engine, hoje - timedelta(days=2))
        eventos = c.get("/agenda/", params={"data": hoje.isoformat(), "dias": 20}).json()["eventos"]
        col = [e for e in eventos if e.get("tipo") == "colostragem_pendente"]
        igg = [e for e in eventos if e.get("tipo") == "igg_pendente"]
        assert any(e["numero_animal"] == "486" for e in col)
        assert any(e["numero_animal"] == "486" for e in igg)
        # Data = parto + 1 dia.
        alvo = next(e for e in col if e["numero_animal"] == "486")
        assert alvo["data"] == (hoje - timedelta(days=1)).isoformat()

    def test_colostragem_preenchida_some_da_agenda(self, client):
        c, engine = client
        hoje = date.today()
        self._parto(engine, hoje - timedelta(days=2))
        # Lança colostro + IgG da bezerra.
        c.post("/sanidade/colostragem", json={
            "numero_animal": "486", "tomou_colostro": True, "litros_colostro": 4,
            "brix_colostro": 26, "brix_soro": 9.0,
        })
        eventos = c.get("/agenda/", params={"data": hoje.isoformat(), "dias": 20}).json()["eventos"]
        assert not any(e.get("tipo") in ("colostragem_pendente", "igg_pendente") and e["numero_animal"] == "486" for e in eventos)

    def test_parto_antigo_nao_gera_lembrete(self, client):
        c, engine = client
        hoje = date.today()
        self._parto(engine, hoje - timedelta(days=60))  # > 30 dias
        eventos = c.get("/agenda/", params={"data": hoje.isoformat(), "dias": 90}).json()["eventos"]
        assert not any(e.get("tipo") in ("colostragem_pendente", "igg_pendente") for e in eventos)


class TestCompraVinculaValor:
    def test_valor_vai_para_a_ficha_do_animal(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="950", sexo="F", ativo=True))
            s.commit()
        r = c.post("/compras-animais/", json={
            "animais": ["950"], "vendedor": "Fazenda Boa Vista", "valor": 3500,
            "tipo_valor": "por_animal", "data_compra": "2026-07-10",
            "codigo_conta_gerencial": "3.10.06",
        })
        assert r.status_code == 200
        with Session(engine) as s:
            a = s.exec(select(Animal).where(Animal.numero == "950")).first()
            assert a.valor == 3500
            assert a.data_entrada == date(2026, 7, 10)
            assert a.proprietario == "Fazenda Boa Vista"
