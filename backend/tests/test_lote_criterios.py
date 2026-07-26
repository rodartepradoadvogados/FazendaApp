"""
Testes dos critérios de seleção de animais por lote (cumulativos) e da
prévia de quantos/quais animais atendem.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, PesagemCorporal, Sanidade, Secagem, Servico


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


class TestPersistenciaCriterios(object):
    def test_cria_lote_com_criterios(self, client):
        c, _ = client
        r = c.post("/lotes/", json={
            "codigo": "05", "nome": "Novilhas aptas",
            "categorias": "novilha", "peso_min": 300, "novilhas_gestantes": False,
        })
        assert r.status_code == 200
        assert r.json()["categorias"] == "novilha"
        assert r.json()["peso_min"] == 300

    def test_edita_lote_atualiza_criterios(self, client):
        c, _ = client
        c.post("/lotes/", json={"codigo": "05", "nome": "X"})
        lote_id = next(l["id"] for l in c.get("/lotes/").json() if l["codigo"] == "05")
        r = c.put(f"/lotes/{lote_id}", json={"codigo": "05", "nome": "X", "em_tratamento": True, "idade_dias_min": 60})
        assert r.json()["em_tratamento"] is True
        assert r.json()["idade_dias_min"] == 60

    def test_rejeita_faixa_peso_invertida(self, client):
        c, _ = client
        r = c.post("/lotes/", json={"codigo": "06", "nome": "X", "peso_min": 400, "peso_max": 300})
        assert r.status_code == 400


class TestPreviewCriterios(object):
    def _seed(self, engine):
        hoje = date.today()
        with Session(engine) as s:
            # Vaca em lactação, DEL 50, produção 25L
            s.add(Animal(numero="1", categoria_completa="Vaca em lactação", categoria_abrev="Vaca",
                         del_dias=50, ult_cl_kg=25, sit_rep="Ins.", data_nasc=hoje - timedelta(days=1500), ativo=True))
            # Novilha apta vazia, sem serviço
            s.add(Animal(numero="2", categoria_completa="Novilha", categoria_abrev="Novilha",
                         sit_rep=None, data_nasc=hoje - timedelta(days=600), ativo=True))
            # Novilha gestante (diagnostico positivo)
            s.add(Animal(numero="3", categoria_completa="Novilha", categoria_abrev="Novilha",
                         sit_rep="Ges.", diagnostico="POSITIVO", data_nasc=hoje - timedelta(days=650), ativo=True))
            # Vaca seca
            s.add(Animal(numero="4", categoria_completa="Vaca seca", categoria_abrev="Vaca",
                         del_dias=None, data_nasc=hoje - timedelta(days=1800), ativo=True))
            s.commit()
            # peso 350kg para a novilha 3 (gestante)
            s.add(PesagemCorporal(numero_matriz="3", data_pesagem=hoje, peso_kg=350))
            # serviço positivo há 100 dias para a novilha 3 (gestante confirmada)
            s.add(Servico(numero_matriz="3", data_servico=hoje - timedelta(days=100), diagnostico="POSITIVO"))
            # aplicação de sanidade recente para o animal 1 (em tratamento)
            s.add(Sanidade(numero_matriz="1", produto="Antibiótico X", data_aplicacao=hoje - timedelta(days=3)))
            # secagem real para o animal 4 — situação produtiva agora é AO VIVO
            # (a partir do Secagem/Parto mais recente), não do texto congelado
            # de categoria_completa (ver fazenda.rules.lote_criterios).
            s.add(Secagem(numero_matriz="4", data_secagem=hoje - timedelta(days=20), motivo="rotina"))
            s.commit()

    def test_filtra_por_status_lactacao(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "status_lactacao": "seca"})
        assert r.json()["animais"] == ["4"]

    def test_filtra_por_categoria(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "categorias": "novilha"})
        assert set(r.json()["animais"]) == {"2", "3"}

    def test_filtra_por_producao(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "producao_min": 20, "producao_max": 30})
        assert r.json()["animais"] == ["1"]

    def test_filtra_por_peso(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "peso_min": 300})
        assert r.json()["animais"] == ["3"]

    def test_novilhas_gestantes(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "novilhas_gestantes": True})
        assert r.json()["animais"] == ["3"]

    def test_novilhas_inseminadas_exclui_gestantes(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "novilhas_inseminadas": True})
        # animal 3 já tem diagnóstico positivo (gestante) -> não entra em "inseminadas"
        assert r.json()["animais"] == []

    def test_em_tratamento(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "em_tratamento": True})
        assert r.json()["animais"] == ["1"]

    def test_idade_dias_min(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "idade_dias_min": 1700})
        assert r.json()["animais"] == ["4"]

    def test_cumulativo_e_logico(self, client):
        c, engine = client
        self._seed(engine)
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "categorias": "novilha", "peso_min": 300})
        assert r.json()["animais"] == ["3"]

    def test_faltando_dias_para_o_parto(self, client):
        c, engine = client
        self._seed(engine)
        # gestação de 283 dias, serviço há 100 dias -> faltam 183 dias
        r = c.post("/lotes/preview", json={"codigo": "?", "nome": "?", "dias_para_parto_min": 170, "dias_para_parto_max": 190})
        assert r.json()["animais"] == ["3"]
