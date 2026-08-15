"""
Protocolo IATF com molde de dias livres (ex.: D0/D8/D10/D12, em vez do
clássico D0/D7/D9) — ver fazenda.rules.protocolo_iatf. Cobre: lançamento cria
as aplicações exatamente nos dias do molde + dia de inseminação calculado
(último dia com hormônio + 2); adicionar_animais_iatf reaproveita os dias do
PRÓPRIO lançamento (não o molde reconsultado); e o flag na_inseminacao em
/protocolo-iatf/ativos não depende mais do dia ser literalmente 11.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ProtocoloIatfAplicacao


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


def _etapa_iatf(dia, produto="Sincrodiol", dose=2.0, unidade="ml", via="Intramuscular"):
    return {"dia": dia, "produto": produto, "dose": dose, "unidade": unidade, "via": via}


def _criar_molde_dias_livres(c):
    r = c.post("/cadastro/protocolos-iatf", json={
        "nome": "Molde D0/D8/D10/D12",
        "etapas": [_etapa_iatf(0), _etapa_iatf(8), _etapa_iatf(10), _etapa_iatf(12)],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestLancamentoComDiasLivres:
    def test_cria_aplicacoes_nos_dias_do_molde_mais_inseminacao(self, client):
        c, engine = client
        pid = _criar_molde_dias_livres(c)
        r = c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": "2026-08-05", "protocolo_id": pid,
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            dias = sorted(
                a.dia for a in s.exec(
                    select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "700")
                ).all()
            )
        # D12 (último hormônio) + 2 = D14 de inseminação — não D11.
        assert dias == [0, 8, 10, 12, 14]

    def test_data_prevista_da_inseminacao_bate_com_d0_mais_dias(self, client):
        c, engine = client
        pid = _criar_molde_dias_livres(c)
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": "2026-08-05", "protocolo_id": pid,
        })
        with Session(engine) as s:
            insem = s.exec(
                select(ProtocoloIatfAplicacao).where(
                    ProtocoloIatfAplicacao.numero_matriz == "700", ProtocoloIatfAplicacao.dia == 14,
                )
            ).one()
        assert insem.data_prevista.isoformat() == "2026-08-19"  # 05/08 + 14 dias

    def test_na_inseminacao_marca_o_ultimo_dia_nao_o_11(self, client):
        # D0 = hoje, para que a "próxima etapa" comece mesmo em D0 (etapas com
        # data já vencida são puladas — ver listar_protocolos_iatf_ativos).
        c, engine = client
        pid = _criar_molde_dias_livres(c)
        c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": date.today().isoformat(), "protocolo_id": pid,
        })
        ativos = c.get("/reproducao/protocolo-iatf/ativos").json()
        lanc = next(p for p in ativos if p["nome_protocolo"].startswith("MOLDE D0/D8/D10/D12"))
        animal = next(a for a in lanc["animais"] if a["numero_matriz"] == "700")
        assert animal["etapa_atual"] == "D0"
        assert animal["na_inseminacao"] is False

        # Confirma D0/D8/D10/D12 manualmente (via banco, mais direto que
        # passar pela Agenda) — só falta a inseminação (D14).
        with Session(engine) as s:
            aps = s.exec(
                select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "700")
            ).all()
            for a in aps:
                if a.dia != 14:
                    a.realizada = True
                    s.add(a)
            s.commit()

        ativos = c.get("/reproducao/protocolo-iatf/ativos").json()
        lanc = next(p for p in ativos if p["nome_protocolo"].startswith("MOLDE D0/D8/D10/D12"))
        animal = next(a for a in lanc["animais"] if a["numero_matriz"] == "700")
        assert animal["etapa_atual"] == "D14"
        assert animal["na_inseminacao"] is True


class TestAdicionarAnimaisRespeitaDiasDoLancamento:
    def test_animal_incluido_depois_entra_nos_mesmos_dias_livres(self, client):
        c, engine = client
        pid = _criar_molde_dias_livres(c)
        r = c.post("/reproducao/protocolo-iatf", json={
            "animais": ["700"], "data_d0": "2026-08-05", "protocolo_id": pid,
        })
        lancamento_id = r.json()["lancamento_id"]

        # Edita o molde DEPOIS de lançado (dias diferentes) — o animal
        # incluído a seguir tem que seguir os dias do LANÇAMENTO já criado,
        # não o molde reconsultado.
        c.put(f"/cadastro/protocolos-iatf/{pid}", json={
            "nome": "Molde D0/D8/D10/D12",
            "etapas": [_etapa_iatf(0), _etapa_iatf(7), _etapa_iatf(9)],
        })

        r2 = c.post(f"/reproducao/protocolo-iatf/{lancamento_id}/animais", json={"animais": ["701"]})
        assert r2.status_code == 200, r2.text

        with Session(engine) as s:
            dias_701 = sorted(
                a.dia for a in s.exec(
                    select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "701")
                ).all()
            )
        assert dias_701 == [0, 8, 10, 12, 14]


class TestAdHocPermaneceClassico:
    def test_lancamento_sem_molde_continua_d0_d7_d9_d11(self, client):
        c, engine = client
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["700"], "data_d0": "2026-08-05"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            dias = sorted(
                a.dia for a in s.exec(
                    select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == "700")
                ).all()
            )
        assert dias == [0, 7, 9, 11]
