"""
Inseminação em lote: vários animais de uma vez, tipo cio natural / IATF /
monta natural, touro por categoria de sêmen e estoque mínimo por categoria.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, EstoqueSemen, ProtocoloIatfAplicacao, ProtocoloIatfLancamento, Servico


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        for n in ["700", "701", "702"]:
            s.add(Animal(numero=n, sit_rep="Vaz. apt.", ativo=True))
        s.add(EstoqueSemen(touro_nome="Hagen", tipo="sexado", doses=3))
        s.add(EstoqueSemen(touro_nome="Coors", tipo="convencional", doses=30))
        s.add(EstoqueSemen(touro_nome="Frederico", tipo="fazenda", doses=0))
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
        permissoes = "reproducao,financeiro,sanidade"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestServicoLote:
    def test_cio_natural_varios_animais(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700", "701"], "data_servico": "2026-07-08", "tipo": "cio_natural", "reprodutor": "Coors",
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 2
        with Session(engine) as s:
            servs = s.exec(select(Servico)).all()
            assert len(servs) == 2
            assert all(sv.tipo_servico == "IA" and sv.protocolo is None for sv in servs)

    def test_monta_natural(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-08", "tipo": "monta_natural", "reprodutor": "Frederico",
        })
        assert r.status_code == 200
        with Session(engine) as s:
            sv = s.exec(select(Servico)).first()
            assert sv.tipo_servico == "Monta natural"

    def test_iatf_sem_protocolo_vai_para_incompativeis(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-08", "tipo": "iatf", "reprodutor": "Coors",
        })
        assert r.status_code == 200
        assert r.json()["incompativeis"] == ["700"]
        assert r.json()["criados"] == 0

    def test_iatf_auto_lanca_protocolo_retroativo(self, client):
        c, engine = client
        r = c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-12", "tipo": "iatf",
            "reprodutor": "Coors", "auto_lancar_iatf": True,
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 1 and r.json()["incompativeis"] == []
        with Session(engine) as s:
            lanc = s.exec(select(ProtocoloIatfLancamento)).first()
            # D0 = serviço − 11 dias, marcado como retroativo.
            assert lanc.data_d0 == date(2026, 7, 12) - timedelta(days=11)
            assert lanc.retroativo is True
            # D11 resolvido pela inseminação (data = serviço).
            d11 = s.exec(select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.dia == 11)).first()
            assert d11.realizada is True

    def test_etapas_retroativas_aparecem_como_pendencia_na_agenda(self, client):
        c, engine = client
        c.post("/reproducao/servico-lote", json={
            "animais": ["700"], "data_servico": "2026-07-12", "tipo": "iatf",
            "reprodutor": "Coors", "auto_lancar_iatf": True,
        })
        # Consulta a agenda numa data DEPOIS de todas as etapas retroativas —
        # num protocolo normal elas ficariam escondidas; retroativo mostra.
        eventos = c.get("/agenda/", params={"data": "2026-07-13", "dias": 30}).json()["eventos"]
        iatf = [e for e in eventos if e.get("tipo") == "protocolo_iatf"]
        dias = sorted(e["dia"] for e in iatf)
        assert dias == [0, 7, 9]  # D0/D7/D9 vencidos aparecem; D11 já foi resolvido


class TestSemenDisponivel:
    def test_categorias_e_minimo(self, client):
        c, engine = client
        d = c.get("/cadastro/estoque-semen/disponivel").json()
        nomes = {t["nome"]: t for t in d["touros"]}
        # Frederico (fazenda) sempre aparece mesmo com 0 dose; Coors/Hagen têm dose.
        assert "Frederico" in nomes and nomes["Frederico"]["tipo"] == "fazenda"
        assert "Coors" in nomes and "Hagen" in nomes
        # Sexado: 3 doses < mínimo 5 → abaixo. Convencional: 30 ≥ 20 → ok.
        assert d["abaixo_minimo"]["sexado"] is True
        assert d["abaixo_minimo"]["convencional"] is False

    def test_alerta_semen_na_agenda(self, client):
        c, engine = client
        eventos = c.get("/agenda/", params={"data": "2026-07-12", "dias": 30}).json()["eventos"]
        semen_baixo = [e for e in eventos if e.get("tipo") == "semen_minimo"]
        assert any("sexado" in e["descricao"] for e in semen_baixo)
