"""
Teste da próxima visita reprodutiva/BST — ancorada no serviço mais recente
do rebanho (não por animal): último serviço em 03/07 -> visita em 24/07.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Servico


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        with Session(engine) as s:
            s.add(Animal(numero="1", sit_rep="Ins.", ativo=True))
            s.add(Animal(numero="2", sit_rep="Ins.", ativo=True))
            s.add(Servico(numero_matriz="1", data_servico=date(2026, 6, 20), ult_ocorrencia=1))
            # Último serviço do rebanho: 03/07 -> visita esperada em 24/07 (21 dias).
            s.add(Servico(numero_matriz="2", data_servico=date(2026, 7, 3), ult_ocorrencia=1))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestProximaVisita:
    def test_ancora_no_servico_mais_recente_do_rebanho(self, client):
        r = client.get("/agenda/", params={"data": "2026-07-08"})
        assert r.json()["proxima_visita_iatf"] == "2026-07-24"

    def test_bst_12_dias_apos_o_mesmo_ancora(self, client):
        r = client.get("/agenda/", params={"data": "2026-07-08"})
        assert r.json()["proxima_visita_bst"] == "2026-07-15"

    def test_sem_servicos_fica_none(self, client):
        # janela sem nenhum Servico cadastrado (banco vazio de serviços num teste isolado)
        engine2 = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine2)

        def _override():
            with Session(engine2) as s:
                yield s

        import main
        main.app.dependency_overrides[database.get_session] = _override
        with TestClient(main.app) as c2:
            r = c2.get("/agenda/", params={"data": "2026-07-08"})
            assert r.json()["proxima_visita_iatf"] is None
