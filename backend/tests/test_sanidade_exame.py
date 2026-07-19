"""
Diagnóstico de exame preventivo (tuberculose, brucelose etc.) lançado via
/sanidade/calendario/cadastrar-preventivo: positivo marca Animal.a_descartar
automaticamente; negativo é informativo ("liberada"); indefinido marca para
repetir o exame (para fins de relatório). Nunca gera aplicação de
medicamento nem baixa de estoque. Cobre também o CRUD de ExameDefinicao
(Configurações > Cadastro > Sanitário > Exames).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal


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
            s.add(Animal(numero="101", sexo="F", ativo=True))
            s.add(Animal(numero="102", sexo="F", ativo=True))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


def _criar_evento_exame(client, exame_definicao_id: int | None = None) -> int:
    r = client.post("/cadastro/eventos-sanitarios", json={
        "nome": "Exame de brucelose", "categoria_preventiva": "exame",
        "exame_definicao_id": exame_definicao_id,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestExameDefinicaoCrud:
    def test_cria_exame_diagnostico(self, client):
        c, _ = client
        r = c.post("/cadastro/exames", json={"nome": "Brucelose (soroaglutinação)", "tipo_resultado": "diagnostico"})
        assert r.status_code == 200, r.text
        assert r.json()["tipo_resultado"] == "diagnostico"

    def test_cria_exame_numerico_com_faixa(self, client):
        c, _ = client
        r = c.post("/cadastro/exames", json={
            "nome": "CCS individual", "tipo_resultado": "numerico",
            "faixa_min": 100, "faixa_max": 400,
            "acao_abaixo": "Sem ação", "acao_dentro": "Monitorar", "acao_acima": "Investigar mastite subclínica",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["faixa_min"] == 100 and d["faixa_max"] == 400

    def test_numerico_sem_faixa_da_400(self, client):
        c, _ = client
        r = c.post("/cadastro/exames", json={"nome": "Sem faixa", "tipo_resultado": "numerico"})
        assert r.status_code == 400

    def test_vincula_principio_ativo(self, client):
        c, _ = client
        p = c.post("/cadastro/principios-ativos", json={"nome": "Antígeno B19"}).json()
        r = c.post("/cadastro/exames", json={"nome": "Brucelose B19 (teste)", "principio_ativo_id": p["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["principio_ativo_nome"] == "Antígeno B19"

    def test_nome_duplicado_da_409(self, client):
        c, _ = client
        c.post("/cadastro/exames", json={"nome": "Tuberculina"})
        r = c.post("/cadastro/exames", json={"nome": "Tuberculina"})
        assert r.status_code == 409

    def test_editar_e_excluir(self, client):
        c, _ = client
        criado = c.post("/cadastro/exames", json={"nome": "Exame X"}).json()
        r = c.put(f"/cadastro/exames/{criado['id']}", json={"nome": "Exame X (revisado)"})
        assert r.status_code == 200
        assert r.json()["nome"] == "Exame X (revisado)"
        r = c.delete(f"/cadastro/exames/{criado['id']}")
        assert r.status_code == 200
        assert r.json()["excluido"] is True

    def test_evento_sanitario_vincula_exame_definicao(self, client):
        c, _ = client
        exame = c.post("/cadastro/exames", json={"nome": "Brucelose"}).json()
        ev_id = _criar_evento_exame(c, exame["id"])
        ev = next(e for e in c.get("/cadastro/eventos-sanitarios").json() if e["id"] == ev_id)
        assert ev["exame_definicao_id"] == exame["id"]
        assert ev["exame_definicao_nome"] == "Brucelose"


class TestDiagnosticoExamePositivoNegativoIndefinido:
    def test_positivo_marca_a_descartar(self, client):
        c, engine = client
        ev_id = _criar_evento_exame(c)
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "frequencia_valor": 0, "resultado_exame": "positivo", "veterinario": "Dr. Carlos",
        })
        assert r.status_code == 200, r.text
        assert r.json()["resultado_exame"]["resultado"] == "positivo"
        resultados = c.get("/sanidade/exames/resultados").json()
        assert len(resultados) == 1
        assert resultados[0]["resultado"] == "positivo"
        assert resultados[0]["numero_matriz"] == "101"
        assert resultados[0]["evento_sanitario_nome"] == "Exame de brucelose"
        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "101")).first()
            assert animal.a_descartar is True

    def test_negativo_nao_marca_a_descartar(self, client):
        c, engine = client
        ev_id = _criar_evento_exame(c)
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["102"],
            "frequencia_valor": 0, "resultado_exame": "negativo",
        })
        assert r.status_code == 200, r.text
        resultados = c.get("/sanidade/exames/resultados").json()
        assert resultados[0]["resultado"] == "negativo"
        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "102")).first()
            assert animal.a_descartar is False

    def test_indefinido_grava_resultado(self, client):
        c, _ = client
        ev_id = _criar_evento_exame(c)
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101", "102"],
            "frequencia_valor": 0, "resultado_exame": "indefinido",
        })
        assert r.status_code == 200, r.text
        resultados = c.get("/sanidade/exames/resultados").json()
        assert len(resultados) == 2
        assert all(x["resultado"] == "indefinido" for x in resultados)

    def test_resultado_invalido_da_400(self, client):
        c, _ = client
        ev_id = _criar_evento_exame(c)
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "frequencia_valor": 0, "resultado_exame": "duvidoso",
        })
        assert r.status_code == 400

    def test_diagnostico_em_evento_nao_exame_da_400(self, client):
        c, _ = client
        r = c.post("/cadastro/eventos-sanitarios", json={"nome": "Vacina Y", "categoria_preventiva": "vacina"})
        ev_id = r.json()["id"]
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "frequencia_valor": 0, "resultado_exame": "positivo",
        })
        assert r.status_code == 400

    def test_nao_gera_aplicacao_nem_baixa_estoque(self, client):
        c, _ = client
        ev_id = _criar_evento_exame(c)
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "frequencia_valor": 0, "resultado_exame": "positivo",
        })
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"] is None
        assert c.get("/sanidade/aplicacoes").json()["total"] == 0

    def test_resultado_numerico_calcula_banda(self, client):
        c, _ = client
        exame = c.post("/cadastro/exames", json={
            "nome": "CCS", "tipo_resultado": "numerico", "faixa_min": 100, "faixa_max": 400,
        }).json()
        ev_id = _criar_evento_exame(c, exame["id"])
        r = c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "frequencia_valor": 0, "resultado_numerico": 550,
        })
        assert r.status_code == 200, r.text
        assert r.json()["resultado_exame"]["banda"] == "acima"
        resultados = c.get("/sanidade/exames/resultados").json()
        assert resultados[0]["valor_numerico"] == 550
        assert resultados[0]["banda"] == "acima"

    def test_filtro_por_evento_e_resultado(self, client):
        c, _ = client
        ev_id = _criar_evento_exame(c)
        c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "frequencia_valor": 0, "resultado_exame": "positivo",
        })
        c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["102"],
            "frequencia_valor": 0, "resultado_exame": "negativo",
        })
        r = c.get("/sanidade/exames/resultados", params={"resultado": "positivo"})
        assert len(r.json()) == 1
        assert r.json()[0]["numero_matriz"] == "101"

    def test_filtro_por_periodo(self, client):
        """#517 — resultados de exame filtráveis por data_de/data_ate."""
        c, _ = client
        ev_id = _criar_evento_exame(c)
        c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": "2026-01-10", "animais": ["101"],
            "frequencia_valor": 0, "resultado_exame": "positivo",
        })
        c.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": "2026-03-10", "animais": ["102"],
            "frequencia_valor": 0, "resultado_exame": "negativo",
        })
        r = c.get("/sanidade/exames/resultados", params={"data_de": "2026-02-01", "data_ate": "2026-04-01"})
        assert len(r.json()) == 1
        assert r.json()[0]["numero_matriz"] == "102"

        r2 = c.get("/sanidade/exames/resultados", params={"data_de": "2026-01-01", "data_ate": "2026-01-31"})
        assert len(r2.json()) == 1
        assert r2.json()[0]["numero_matriz"] == "101"
