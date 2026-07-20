"""
Testes do lançamento de Indução de Lactação (protocolo/etapas + cálculo de
data_prevista a partir de dia_inicial) — gap identificado na padronização em
D0 dos protocolos sanitários (jul/2026): não havia nenhum teste cobrindo
`ProtocoloInducaoLactacao`/`lancar_inducao_lactacao` antes desta mudança.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ProtocoloInducaoAplicacao


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


def _etapa_manejo(dia, produto="Adaptação na ordenha"):
    return {"dia": dia, "tipo": "manejo", "produto": produto}


class TestCadastroProtocoloInducao:
    def test_cria_protocolo_com_dia_inicial_0(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução teste D0", "dia_inicial": 0,
            "etapas": [_etapa_manejo(0), _etapa_manejo(1), _etapa_manejo(2)],
        })
        assert r.status_code == 200, r.json()
        corpo = r.json()
        assert corpo["dia_inicial"] == 0
        assert [e["dia"] for e in corpo["etapas"]] == [0, 1, 2]

    def test_cria_protocolo_com_dia_inicial_1(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução teste D1", "dia_inicial": 1,
            "etapas": [_etapa_manejo(1), _etapa_manejo(2), _etapa_manejo(3)],
        })
        assert r.status_code == 200, r.json()
        assert r.json()["dia_inicial"] == 1


class TestLancamentoInducaoLactacao:
    def _protocolo_d0(self, c):
        return c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução D0", "dia_inicial": 0,
            "etapas": [_etapa_manejo(0), _etapa_manejo(1), _etapa_manejo(2)],
        }).json()["id"]

    def _protocolo_d1(self, c):
        return c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução D1", "dia_inicial": 1,
            "etapas": [_etapa_manejo(1), _etapa_manejo(2), _etapa_manejo(3)],
        }).json()["id"]

    def test_lanca_inducao_dia_inicial_0_gera_datas_a_partir_do_d0(self, client):
        c, engine = client
        protocolo_id = self._protocolo_d0(c)
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": protocolo_id, "animais": ["800"], "data_d0": "2026-03-01",
        })
        assert r.status_code == 201, r.json()
        corpo = r.json()
        assert corpo["eventos_criados"] == 3

        with Session(engine) as s:
            aplicacoes = s.exec(
                select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.numero_matriz == "800")
            ).all()
            datas = sorted(a.data_prevista.isoformat() for a in aplicacoes)
            assert datas == ["2026-03-01", "2026-03-02", "2026-03-03"]  # D0=início, D1=+1, D2=+2

    def test_lanca_inducao_dia_inicial_1_gera_as_mesmas_datas(self, client):
        # Mesmo cronograma relativo (3 dias seguidos a partir do 1º dia), só
        # que rotulado D1/D2/D3 em vez de D0/D1/D2 — o offset de datas
        # (dia - dia_inicial) deve ser idêntico ao caso dia_inicial=0 acima.
        c, engine = client
        protocolo_id = self._protocolo_d1(c)
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": protocolo_id, "animais": ["801"], "data_d0": "2026-03-01",
        })
        assert r.status_code == 201, r.json()

        with Session(engine) as s:
            aplicacoes = s.exec(
                select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.numero_matriz == "801")
            ).all()
            datas = sorted(a.data_prevista.isoformat() for a in aplicacoes)
            assert datas == ["2026-03-01", "2026-03-02", "2026-03-03"]

    def test_lanca_inducao_para_varios_animais(self, client):
        c, engine = client
        protocolo_id = self._protocolo_d0(c)
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": protocolo_id, "animais": ["800", "801", "802"], "data_d0": "2026-03-01",
        })
        assert r.status_code == 201, r.json()
        assert r.json()["animais"] == 3
        assert r.json()["eventos_criados"] == 9  # 3 etapas x 3 animais

    def test_rejeita_protocolo_inexistente(self, client):
        c, engine = client
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": 999999, "animais": ["800"], "data_d0": "2026-03-01",
        })
        assert r.status_code == 404
