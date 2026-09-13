"""
Indução de cio (PGF2α/Cloprostenol) — estímulo hormonal lançado à parte de
protocolos IATF, inseminação e diagnóstico (ver reproducao.py,
ATIVIDADE_INDUCAO_CIO). Guardado como Sanidade com atividade própria, para
gerar histórico sem misturar com Servico/ProtocoloIatf* nem afetar métricas
reprodutivas (taxa de concepção etc.).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from sqlmodel import select

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import Estoque, Sanidade


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
        with Session(engine) as s:
            s.add(Estoque(nome="Cloprostenol", quantidade=100.0, unidade="ml"))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


class TestRegistrarInducaoCio:
    def test_registra_para_varios_animais_e_gera_historico(self, client):
        c, engine = client
        r = c.post("/reproducao/inducao-cio", json={
            "numeros_matriz": ["101", "102"], "data_aplicacao": "2026-08-10", "produto": "Cloprostenol",
            "dose": 2.0, "unidade": "ml", "via": "IM", "responsavel": "João",
        })
        assert r.status_code == 201, r.text
        assert r.json()["aplicados"] == 2

        with Session(engine) as s:
            lancamentos = s.exec(select(Sanidade).where(Sanidade.atividade == "Indução de cio")).all()
            assert sorted(l.numero_matriz for l in lancamentos) == ["101", "102"]
            assert all(l.via == "IM" and l.responsavel == "João" for l in lancamentos)

    def test_baixa_estoque_quando_dose_e_unidade_informados(self, client):
        c, engine = client
        c.post("/reproducao/inducao-cio", json={
            "numeros_matriz": ["101"], "data_aplicacao": "2026-08-10", "produto": "Cloprostenol",
            "dose": 5.0, "unidade": "ml",
        })
        item = c.get("/estoque/").json()["itens"]
        cloprostenol = next(i for i in item if i["nome"] == "Cloprostenol")
        assert cloprostenol["quantidade"] == 95.0

    def test_nao_baixa_estoque_sem_dose(self, client):
        c, engine = client
        c.post("/reproducao/inducao-cio", json={"numeros_matriz": ["101"], "data_aplicacao": "2026-08-10"})
        item = c.get("/estoque/").json()["itens"]
        cloprostenol = next(i for i in item if i["nome"] == "Cloprostenol")
        assert cloprostenol["quantidade"] == 100.0

    def test_sem_animais_da_400(self, client):
        c, _ = client
        r = c.post("/reproducao/inducao-cio", json={"numeros_matriz": [], "data_aplicacao": "2026-08-10"})
        assert r.status_code == 400

    def test_listar_ordenado_por_data_desc(self, client):
        c, _ = client
        c.post("/reproducao/inducao-cio", json={"numeros_matriz": ["101"], "data_aplicacao": "2026-08-01"})
        c.post("/reproducao/inducao-cio", json={"numeros_matriz": ["102"], "data_aplicacao": "2026-08-10"})
        lista = c.get("/reproducao/inducao-cio").json()
        assert [l["numero_matriz"] for l in lista] == ["102", "101"]

    def test_excluir_lancamento(self, client):
        c, engine = client
        c.post("/reproducao/inducao-cio", json={"numeros_matriz": ["101"], "data_aplicacao": "2026-08-10"})
        lid = c.get("/reproducao/inducao-cio").json()[0]["id"]
        assert c.delete(f"/reproducao/inducao-cio/{lid}").status_code == 200
        assert c.get("/reproducao/inducao-cio").json() == []

    def test_nao_mistura_com_servico(self, client):
        """Não pode criar nenhum Servico (inseminação) — é só Sanidade com
        atividade própria, sem tocar em Servico/ProtocoloIatf*."""
        c, engine = client
        c.post("/reproducao/inducao-cio", json={"numeros_matriz": ["101"], "data_aplicacao": "2026-08-10"})
        with Session(engine) as s:
            from fazenda.models import Servico
            assert s.exec(select(Servico)).all() == []
