"""
Protocolo de indução de lactação: ao confirmar o dia na Agenda, o usuário
escolhe QUAL medicamento/frasco em estoque foi usado (mesmo mecanismo do
protocolo IATF) — a baixa vai para o frasco escolhido (estoque_id), não mais
resolvida só pelo nome do produto/princípio.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Estoque, PrincipioAtivo, ProtocoloInducaoLactacao, ProtocoloInducaoLactacaoEtapa, Sanidade,
)


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
        yield c, engine

    main.app.dependency_overrides.clear()


def _protocolo_com_dois_frascos(engine):
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Benzoato de Estradiol", unidade_base="ml")
        s.add(pa); s.commit(); s.refresh(pa)
        a = Estoque(nome="Sincrodiol", principio_ativo_id=pa.id, quantidade=50, unidade="ml", estoque_inicializado=True)
        b = Estoque(nome="Gonadiol", principio_ativo_id=pa.id, quantidade=50, unidade="ml", estoque_inicializado=True)
        s.add(a); s.add(b)

        protocolo = ProtocoloInducaoLactacao(nome="Protocolo teste", dia_inicial=0)
        s.add(protocolo); s.commit(); s.refresh(protocolo)
        s.add(ProtocoloInducaoLactacaoEtapa(
            protocolo_id=protocolo.id, dia=0, tipo="medicamento", produto="Sincrodiol",
            dose=2, unidade="ml", via="Intramuscular", principio_ativo_id=pa.id,
        ))
        s.commit()
        return protocolo.id, a.id, b.id


class TestQualMedicamentoNoConfirm:
    def test_evento_expoe_medicamentos_com_opcoes(self, client):
        c, engine = client
        protocolo_id, a_id, b_id = _protocolo_com_dois_frascos(engine)
        c.post("/producao/inducao-lactacao", json={
            "protocolo_id": protocolo_id, "animais": ["900"], "data_d0": "2026-08-04",
        })
        eventos = c.get("/agenda/", params={"data": "2026-08-04", "dias": 5}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_inducao" and e["dia"] == 0)
        assert d0["medicamentos_opcoes"], "o dia deve expor os medicamentos estruturados"
        opcoes = {o["nome"] for o in d0["medicamentos_opcoes"][0]["opcoes"]}
        assert {"Sincrodiol", "Gonadiol"} <= opcoes  # os dois frascos do princípio

    def test_confirmar_com_medicamento_abate_do_frasco_escolhido(self, client):
        c, engine = client
        protocolo_id, a_id, b_id = _protocolo_com_dois_frascos(engine)
        c.post("/producao/inducao-lactacao", json={
            "protocolo_id": protocolo_id, "animais": ["900", "901"], "data_d0": "2026-08-04",
        })
        eventos = c.get("/agenda/", params={"data": "2026-08-04", "dias": 5}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_inducao" and e["dia"] == 0)
        # Confirma escolhendo o frasco B (Gonadiol) para as 2 vacas.
        r = c.post("/agenda/realizados", json={
            "evento_id": d0["id"],
            "medicamentos": [{"produto": "Gonadiol", "estoque_id": b_id, "dose": 2, "unidade": "ml"}],
        })
        assert r.status_code == 200
        with Session(engine) as s:
            assert s.get(Estoque, a_id).quantidade == 50        # Sincrodiol intacto
            assert s.get(Estoque, b_id).quantidade == 50 - 4    # Gonadiol: 2ml × 2 vacas
            sanidades = s.exec(select(Sanidade)).all()
            assert {sa.produto for sa in sanidades} == {"Gonadiol"}

    def test_sem_escolha_cai_no_medicamento_cadastrado(self, client):
        c, engine = client
        protocolo_id, a_id, b_id = _protocolo_com_dois_frascos(engine)
        c.post("/producao/inducao-lactacao", json={
            "protocolo_id": protocolo_id, "animais": ["900"], "data_d0": "2026-08-04",
        })
        eventos = c.get("/agenda/", params={"data": "2026-08-04", "dias": 5}).json()["eventos"]
        d0 = next(e for e in eventos if e.get("tipo") == "protocolo_inducao" and e["dia"] == 0)
        r = c.post("/agenda/realizados", json={"evento_id": d0["id"]})
        assert r.status_code == 200
        with Session(engine) as s:
            # Comportamento antigo: resolve pelo nome exato cadastrado no lançamento (Sincrodiol).
            assert s.get(Estoque, a_id).quantidade == 50 - 2
            assert s.get(Estoque, b_id).quantidade == 50
