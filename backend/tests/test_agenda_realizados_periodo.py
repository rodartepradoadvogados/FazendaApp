"""
GET /agenda/realizados — lista as marcações genéricas de conclusão
(EventoRealizado) num período, para o card "Concluídos no período" da
Agenda (sessão 1, Frente C, C7-C10). Cobre: filtro de/até por `marcado_em`,
isolamento por fazenda_id (mesmo padrão dos vizinhos do router) e o rótulo
amigável por prefixo — sem inventar nada para um prefixo desconhecido.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContratoFazenda, Fazenda
from fazenda.models.sistema import EventoRealizado


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

    # Fazenda 1 com contrato ativo — o router de Agenda exige isso
    # (exigir_contrato_ativo) sempre que get_fazenda_atual_id resolve um id
    # de verdade, e o teste fixa o id para poder exercitar o filtro por
    # fazenda_id do endpoint novo.
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um", ativa=True))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.commit()

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def test_filtra_por_periodo_e_isola_por_fazenda(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        # Dentro do período (últimos 7 dias, prefixo mapeado).
        s.add(EventoRealizado(evento_id="pesagem_1_2026-01-01", marcado_em=datetime.combine(hoje - timedelta(days=2), datetime.min.time()), fazenda_id=1))
        # Fora do período (10 dias atrás).
        s.add(EventoRealizado(evento_id="pesagem_2_2026-01-01", marcado_em=datetime.combine(hoje - timedelta(days=10), datetime.min.time()), fazenda_id=1))
        # De outra fazenda — não pode vazar.
        s.add(EventoRealizado(evento_id="pesagem_3_2026-01-01", marcado_em=datetime.combine(hoje - timedelta(days=1), datetime.min.time()), fazenda_id=2))
        s.commit()

    de = (hoje - timedelta(days=7)).isoformat()
    ate = hoje.isoformat()
    r = c.get(f"/agenda/realizados?de={de}&ate={ate}")
    assert r.status_code == 200, r.text
    ids = {item["evento_id"] for item in r.json()}
    assert ids == {"pesagem_1_2026-01-01"}


def test_rotulo_conhecido_e_fallback_sem_inventar(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(EventoRealizado(evento_id="sugestao_movimentacao_900_sem_lote", marcado_em=datetime.combine(hoje, datetime.min.time()), fazenda_id=1))
        s.add(EventoRealizado(evento_id="algo_totalmente_novo_123", marcado_em=datetime.combine(hoje, datetime.min.time()), fazenda_id=1))
        s.commit()

    r = c.get(f"/agenda/realizados?de={hoje.isoformat()}&ate={hoje.isoformat()}")
    assert r.status_code == 200, r.text
    por_id = {item["evento_id"]: item["rotulo"] for item in r.json()}
    assert por_id["sugestao_movimentacao_900_sem_lote"] == "Sugestão de movimentação de lote"
    # Prefixo desconhecido: sem rótulo inventado — o front cai pro evento_id cru.
    assert por_id["algo_totalmente_novo_123"] is None


def test_sem_filtro_de_data_devolve_tudo_da_fazenda(client):
    c, engine = client
    with Session(engine) as s:
        s.add(EventoRealizado(evento_id="pesagem_9_2020-01-01", marcado_em=datetime(2020, 1, 1), fazenda_id=1))
        s.commit()

    r = c.get("/agenda/realizados")
    assert r.status_code == 200, r.text
    assert any(item["evento_id"] == "pesagem_9_2020-01-01" for item in r.json())
