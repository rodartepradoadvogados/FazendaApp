"""
GET /reproducao/ciclos-21-dias — o relatório de risco de prenhez em ciclos de
21 dias (BREDSUM\\E), que substituiu o cálculo fechado ancorado no D11.

Aqui se testa a integração: carregamento do rebanho, âncora configurável e o
formato da resposta. As regras em si (R1–R9) são testadas sem banco em
`test_programa_reprodutivo.py`.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Parto, Servico


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeAdmin:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _vaca(s, numero, *, parto=date(2025, 10, 1), **kw):
    s.add(Animal(numero=numero, sexo="F", ativo=True, eh_semen=False,
                 categoria_abrev="Vaca", data_nasc=date(2022, 1, 1), **kw))
    s.add(Parto(numero_matriz=numero, data_parto=parto))


class TestCiclos21DiasAPI:
    def test_denominador_inclui_a_vaca_que_ninguem_inseminou(self, client):
        """O erro central do cálculo antigo, agora coberto de ponta a ponta."""
        c, engine = client
        with Session(engine) as s:
            _vaca(s, "10")
            _vaca(s, "11")
            _vaca(s, "12")
            s.add(Servico(numero_matriz="10", data_servico=date(2026, 1, 5), diagnostico="POSITIVO"))
            s.add(Servico(numero_matriz="11", data_servico=date(2026, 1, 6), diagnostico="NEGATIVO"))
            s.commit()

        r = c.get("/reproducao/ciclos-21-dias", params={
            "ancora": "2026-01-01", "modo": "inicio", "n_ciclos": 1,
        })
        assert r.status_code == 200, r.text
        ciclo = r.json()["ciclos"][0]
        assert ciclo["br_elig"] == 3, "as três elegíveis, inclusive a nunca inseminada"
        assert ciclo["bred"] == 2
        assert ciclo["taxa_servico"] == round(100 * 2 / 3, 1)
        assert ciclo["preg"] == 1

    def test_drill_down_lista_quem_entrou_em_cada_balde(self, client):
        c, engine = client
        with Session(engine) as s:
            _vaca(s, "10")
            _vaca(s, "11")
            s.add(Servico(numero_matriz="10", data_servico=date(2026, 1, 5), diagnostico="POSITIVO"))
            s.commit()

        j = c.get("/reproducao/ciclos-21-dias", params={
            "ancora": "2026-01-01", "modo": "inicio", "n_ciclos": 1,
        }).json()
        animais = j["ciclos"][0]["animais"]
        assert animais["br_elig"] == ["10", "11"]
        assert animais["bred"] == ["10"]
        assert animais["preg"] == ["10"]

    def test_gestante_e_descartada_ficam_fora_do_denominador(self, client):
        c, engine = client
        with Session(engine) as s:
            _vaca(s, "10")
            _vaca(s, "20", parto=date(2025, 8, 1))   # gestante de ciclo anterior
            _vaca(s, "30", a_descartar=True)
            s.add(Servico(numero_matriz="20", data_servico=date(2025, 10, 1), diagnostico="POSITIVO"))
            s.commit()

        j = c.get("/reproducao/ciclos-21-dias", params={
            "ancora": "2026-01-01", "modo": "inicio", "n_ciclos": 1,
        }).json()
        assert j["ciclos"][0]["animais"]["br_elig"] == ["10"]

    def test_ancora_no_fim_conta_para_tras(self, client):
        c, _ = client
        j = c.get("/reproducao/ciclos-21-dias", params={
            "ancora": "2026-03-04", "modo": "fim", "n_ciclos": 3,
        }).json()
        assert j["periodo"]["fim"] == "2026-03-04"
        assert j["periodo"]["inicio"] == "2026-01-01"
        assert [x["ciclo"] for x in j["ciclos"]] == [1, 2, 3]

    def test_filtro_por_categoria_separa_vaca_de_novilha(self, client):
        c, engine = client
        with Session(engine) as s:
            _vaca(s, "10")
            s.add(Animal(numero="90", sexo="F", ativo=True, eh_semen=False,
                         categoria_abrev="Novilha", data_nasc=date(2024, 1, 1)))
            s.commit()

        so_vacas = c.get("/reproducao/ciclos-21-dias", params={
            "ancora": "2026-01-01", "modo": "inicio", "n_ciclos": 1, "categoria": "vaca",
        }).json()
        assert so_vacas["ciclos"][0]["animais"]["br_elig"] == ["10"]
        assert so_vacas["resumo"]["animais_avaliados"] == 1

    def test_modo_invalido_da_400(self, client):
        c, _ = client
        r = c.get("/reproducao/ciclos-21-dias", params={"ancora": "2026-01-01", "modo": "meio"})
        assert r.status_code == 400

    def test_resposta_traz_metas_parametros_e_a_ressalva_historica(self, client):
        c, _ = client
        j = c.get("/reproducao/ciclos-21-dias", params={
            "ancora": "2026-01-01", "modo": "inicio", "n_ciclos": 1,
        }).json()
        assert j["parametros"]["dias_minimos_no_ciclo"] == 11
        assert j["parametros"]["dias_resultado_conhecido"] == 28
        assert "metas" in j
        assert "a descartar" in j["ressalva_historica"]
