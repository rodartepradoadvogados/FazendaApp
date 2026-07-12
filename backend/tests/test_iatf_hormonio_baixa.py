"""
Protocolo IATF estruturado por medicamento: ao lançar com hormônios por dia
(ex.: D0 = 1ml SincroCP + 2ml Estron), a descrição de cada dia passa a listar
os produtos, e ao confirmar o dia na Agenda o estoque é baixado (dose × nº de
vacas confirmadas) e uma aplicação de Sanidade é registrada por vaca.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, MovimentoEstoque, ProtocoloIatfHormonio, Sanidade


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Estoque(nome="SincroCP", quantidade=100, unidade="ml"))
        s.add(Estoque(nome="Estron", quantidade=100, unidade="ml"))
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


def _lancar_com_hormonios(c, animais, data_d0="2026-07-08"):
    return c.post("/reproducao/protocolo-iatf", json={
        "animais": animais, "data_d0": data_d0, "protocolo": "IATF teste",
        "hormonios": [
            {"dia": 0, "produto": "SincroCP", "dose": 1, "unidade": "ml", "via": "Intramuscular"},
            {"dia": 0, "produto": "Estron", "dose": 2, "unidade": "ml", "via": "Intramuscular"},
        ],
    }).json()


class TestLancamentoComHormonios:
    def test_persiste_hormonios(self, client):
        c, engine = client
        _lancar_com_hormonios(c, ["700"])
        with Session(engine) as s:
            hs = s.exec(select(ProtocoloIatfHormonio).where(ProtocoloIatfHormonio.dia == 0)).all()
            assert {h.produto for h in hs} == {"SincroCP", "Estron"}

    def test_descricao_do_dia_lista_produtos(self, client):
        c, engine = client
        _lancar_com_hormonios(c, ["700"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        assert "SincroCP" in d0["hormonio"] and "Estron" in d0["hormonio"]


class TestConfirmarBaixaEstoque:
    def test_confirmar_grupo_baixa_estoque_e_cria_sanidade(self, client):
        c, engine = client
        _lancar_com_hormonios(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        r = c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        assert r.status_code == 200

        with Session(engine) as s:
            sincro = s.exec(select(Estoque).where(Estoque.nome == "SincroCP")).first()
            estron = s.exec(select(Estoque).where(Estoque.nome == "Estron")).first()
            # 2 vacas confirmadas: 1ml×2 e 2ml×2.
            assert sincro.quantidade == 100 - 2
            assert estron.quantidade == 100 - 4

            sanidades = s.exec(select(Sanidade)).all()
            # 2 produtos × 2 vacas = 4 registros de Sanidade.
            assert len(sanidades) == 4
            assert {sa.numero_matriz for sa in sanidades} == {"700", "701"}

            movs = s.exec(select(MovimentoEstoque)).all()
            assert len(movs) == 2  # um por hormônio

    def test_confirmar_parcial_baixa_so_pela_vaca_confirmada(self, client):
        c, engine = client
        _lancar_com_hormonios(c, ["700", "701"])
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)

        c.post("/agenda/realizados", json={"evento_id": d0["id"], "animais": ["700"]})

        with Session(engine) as s:
            sincro = s.exec(select(Estoque).where(Estoque.nome == "SincroCP")).first()
            estron = s.exec(select(Estoque).where(Estoque.nome == "Estron")).first()
            assert sincro.quantidade == 100 - 1  # só 1 vaca
            assert estron.quantidade == 100 - 2
            sanidades = s.exec(select(Sanidade)).all()
            assert len(sanidades) == 2  # 2 produtos × 1 vaca
            assert {sa.numero_matriz for sa in sanidades} == {"700"}

    def test_sem_hormonios_nao_baixa_estoque(self, client):
        c, engine = client
        c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-07-08", "protocolo": "IATF simples"})
        eventos = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_iatf" and e["dia"] == 0)
        c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        with Session(engine) as s:
            assert s.exec(select(Sanidade)).all() == []
            assert s.exec(select(MovimentoEstoque)).all() == []
