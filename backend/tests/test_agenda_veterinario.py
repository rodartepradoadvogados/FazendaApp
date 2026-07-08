"""
Testes da agenda/roteiro do veterinário do serviço — classificação do
rebanho em 9 listas.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, PesagemCorporal, Servico

HOJE = date(2026, 7, 8)


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


def _add_animal(engine, numero, categoria_abrev, sexo="F", eh_semen=False, ativo=True):
    with Session(engine) as s:
        s.add(Animal(numero=numero, categoria_abrev=categoria_abrev, sexo=sexo, eh_semen=eh_semen, ativo=ativo))
        s.commit()


def _add_peso(engine, numero, peso):
    with Session(engine) as s:
        s.add(PesagemCorporal(numero_matriz=numero, data_pesagem=HOJE, peso_kg=peso))
        s.commit()


def _add_servico(engine, numero, dias_atras, **kwargs):
    with Session(engine) as s:
        s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), **kwargs))
        s.commit()


class TestExclusoes:
    def test_macho_nunca_entra(self, client):
        c, engine = client
        _add_animal(engine, "1", "Touro", sexo="M")
        r = c.get("/reproducao/agenda-veterinario")
        assert all(a["numero_matriz"] != "1" for lst in r.json()["listas"].values() for a in lst)

    def test_bezerra_nunca_entra(self, client):
        c, engine = client
        _add_animal(engine, "2", "Bezerra")
        r = c.get("/reproducao/agenda-veterinario")
        assert all(a["numero_matriz"] != "2" for lst in r.json()["listas"].values() for a in lst)

    def test_novilha_abaixo_260kg_nunca_entra(self, client):
        c, engine = client
        _add_animal(engine, "3", "Novilha")
        _add_peso(engine, "3", 200)
        r = c.get("/reproducao/agenda-veterinario")
        assert all(a["numero_matriz"] != "3" for lst in r.json()["listas"].values() for a in lst)


class TestInseminadas:
    def test_1_a_29_dias(self, client):
        c, engine = client
        _add_animal(engine, "10", "Vaca")
        _add_servico(engine, "10", 10)
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "10" for a in r.json()["listas"]["inseminadas_1_29"])

    def test_30_a_59_sem_toque_fica_atrasada(self, client):
        c, engine = client
        _add_animal(engine, "11", "Vaca")
        _add_servico(engine, "11", 40)
        r = c.get("/reproducao/agenda-veterinario")
        item = next(a for a in r.json()["listas"]["inseminadas_30_59"] if a["numero_matriz"] == "11")
        assert item["atrasada"] is True

    def test_60_mais_sem_reconfirmacao_fica_atrasada(self, client):
        c, engine = client
        _add_animal(engine, "12", "Vaca")
        _add_servico(engine, "12", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        item = next(a for a in r.json()["listas"]["inseminadas_60_mais"] if a["numero_matriz"] == "12")
        assert item["atrasada"] is True
        assert item["tocada"] is True

    def test_gestante_confirmada_sai_das_listas_1_2_3(self, client):
        c, engine = client
        _add_animal(engine, "13", "Vaca")
        _add_servico(engine, "13", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=5), diagnostico_reconfirmacao="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        listas = r.json()["listas"]
        assert not any(a["numero_matriz"] == "13" for a in listas["inseminadas_60_mais"])
        assert any(a["numero_matriz"] == "13" for a in listas["vacas_gestantes"])


class TestNovilhas:
    def test_apta_vazia_300kg_sem_servico(self, client):
        c, engine = client
        _add_animal(engine, "20", "Novilha")
        _add_peso(engine, "20", 320)
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "20" for a in r.json()["listas"]["novilhas_aptas_vazias"])

    def test_verificar_aptidao_260_a_299(self, client):
        c, engine = client
        _add_animal(engine, "21", "Novilha")
        _add_peso(engine, "21", 280)
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "21" for a in r.json()["listas"]["verificar_aptidao"])

    def test_novilha_gestante_confirmada(self, client):
        c, engine = client
        _add_animal(engine, "22", "Novilha")
        _add_peso(engine, "22", 350)
        _add_servico(engine, "22", 70, data_diagnostico=HOJE - timedelta(days=40), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=5), diagnostico_reconfirmacao="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "22" for a in r.json()["listas"]["novilhas_gestantes"])

    def test_inseminada_nao_reconfirmada_nao_entra_em_gestantes(self, client):
        c, engine = client
        _add_animal(engine, "23", "Novilha")
        _add_peso(engine, "23", 350)
        _add_servico(engine, "23", 40, data_diagnostico=HOJE - timedelta(days=10), diagnostico="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        assert not any(a["numero_matriz"] == "23" for a in r.json()["listas"]["novilhas_gestantes"])


class TestPreParto:
    def test_gestante_31_a_60_dias_para_parto(self, client):
        c, engine = client
        _add_animal(engine, "30", "Vaca")
        # gestação de 283 dias; faltando 45 dias -> serviço há 238 dias
        _add_servico(engine, "30", 238, data_diagnostico=HOJE - timedelta(days=200), diagnostico="POSITIVO",
                     data_reconfirmacao=HOJE - timedelta(days=170), diagnostico_reconfirmacao="POSITIVO")
        r = c.get("/reproducao/agenda-veterinario")
        assert any(a["numero_matriz"] == "30" for a in r.json()["listas"]["verificar_pre_parto"])


class TestPendentesClassificacao:
    def test_vaca_sem_servico_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "40", "Vaca")
        r = c.get("/reproducao/agenda-veterinario")
        item = next(a for a in r.json()["listas"]["pendentes_classificacao"] if a["numero_matriz"] == "40")
        assert "motivo" in item and item["motivo"]

    def test_novilha_sem_peso_fica_pendente(self, client):
        c, engine = client
        _add_animal(engine, "41", "Novilha")
        r = c.get("/reproducao/agenda-veterinario")
        item = next(a for a in r.json()["listas"]["pendentes_classificacao"] if a["numero_matriz"] == "41")
        assert "peso" in item["motivo"].lower()
