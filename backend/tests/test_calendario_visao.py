"""
Card CALENDÁRIO do calendário sanitário (GET /sanidade/calendario/visao) —
projeta ocorrências das regras num intervalo, estima animais por tipo de
regra e agrupa ocorrências próximas para sugerir chamar o veterinário.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database


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


HOJE = date.today()


def _visao(c, dias_ate=90):
    r = c.get(f"/sanidade/calendario/visao?data_inicio={HOJE.isoformat()}&data_fim={(HOJE + timedelta(days=dias_ate)).isoformat()}")
    assert r.status_code == 200, r.text
    return r.json()


class TestOcorrenciaPorEpoca:
    def test_sem_historico_animais_e_none(self, client):
        c, _ = client
        ev = c.post("/cadastro/eventos-sanitarios", json={"nome": "Leptospirose", "categoria_preventiva": "vacina"}).json()
        c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev["id"], "categoria_alvo": "Vacas", "produto": "Lepto Forte",
            "frequencia_valor": 12, "frequencia_unidade": "meses", "data_evento": (HOJE + timedelta(days=10)).isoformat(),
        })
        visao = _visao(c)
        ocorrencias = [o for j in visao["janelas"] for o in j["eventos"]]
        assert any(o["evento_sanitario_nome"] == "Leptospirose" for o in ocorrencias)
        alvo = next(o for o in ocorrencias if o["evento_sanitario_nome"] == "Leptospirose")
        assert alvo["animais"] is None
        assert alvo["estimativa"] is False

    def test_com_historico_usa_ultima_aplicacao_como_estimativa(self, client):
        c, engine = client
        ev = c.post("/cadastro/eventos-sanitarios", json={"nome": "Leptospirose", "categoria_preventiva": "vacina"}).json()
        c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev["id"], "categoria_alvo": "Vacas", "produto": "Lepto Forte",
            "frequencia_valor": 12, "frequencia_unidade": "meses", "data_evento": (HOJE + timedelta(days=10)).isoformat(),
        })
        from fazenda.models import Sanidade
        with Session(engine) as s:
            for numero in ("A1", "A2", "A3"):
                s.add(Sanidade(
                    numero_matriz=numero, produto="Lepto Forte", natureza="preventivo",
                    data_aplicacao=HOJE - timedelta(days=300),
                ))
            s.commit()
        visao = _visao(c)
        ocorrencias = [o for j in visao["janelas"] for o in j["eventos"]]
        alvo = next(o for o in ocorrencias if o["evento_sanitario_nome"] == "Leptospirose")
        assert alvo["animais"] == 3
        assert alvo["estimativa"] is True
        assert alvo["estimativa_base"] == "ultima_aplicacao"


class TestOcorrenciaPorGatilho:
    def test_conta_animais_reais_no_gatilho(self, client):
        c, engine = client
        from fazenda.models import Animal
        with Session(engine) as s:
            for numero in ("N1", "N2"):
                s.add(Animal(numero=numero, sexo="F", ativo=True, data_nasc=HOJE - timedelta(days=60)))
            s.commit()
        ev = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina Brucelose", "tipo_agendamento": "evento", "gatilho": "novilha_apta",
            "gatilho_idade_meses": 3, "categoria_preventiva": "vacina",
        }).json()
        c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev["id"], "categoria_alvo": "Novilhas 3 meses",
            "frequencia_valor": 60, "frequencia_unidade": "dias", "data_evento": HOJE.isoformat(),
        })
        visao = _visao(c)
        ocorrencias = [o for j in visao["janelas"] for o in j["eventos"]]
        alvo = next(o for o in ocorrencias if o["evento_sanitario_nome"] == "Vacina Brucelose")
        assert alvo["animais"] == 2
        assert alvo["estimativa"] is False


class TestOcorrenciaComCronograma:
    def test_usa_contagem_real_do_cronograma_aberto(self, client):
        c, _ = client
        ev = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina IBR", "tipo_agendamento": "evento", "gatilho": "novilha_apta",
            "gatilho_idade_meses": 3, "categoria_preventiva": "vacina",
        }).json()
        cal = c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev["id"], "categoria_alvo": "Novilhas 3 meses",
            "frequencia_valor": 60, "frequencia_unidade": "dias", "data_evento": (HOJE + timedelta(days=5)).isoformat(),
            "usa_cronograma": True,
        }).json()
        visao = _visao(c)
        ocorrencias = [o for j in visao["janelas"] for o in j["eventos"]]
        alvo = next(o for o in ocorrencias if o["calendario_sanitario_id"] == cal["id"])
        assert alvo["cronograma"] is not None
        assert alvo["cronograma"]["status"] == "aberto"
        assert alvo["animais"] == 0  # nenhum animal sugerido ainda


class TestAgrupamento:
    def test_agrupa_ocorrencias_proximas_e_soma_animais(self, client):
        c, engine = client
        from fazenda.models import Sanidade
        with Session(engine) as s:
            s.add(Sanidade(numero_matriz="V1", produto="Vacina A", natureza="preventivo", data_aplicacao=HOJE - timedelta(days=300)))
            for n in ("V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10", "V11", "V12"):
                s.add(Sanidade(numero_matriz=n, produto="Vacina B", natureza="preventivo", data_aplicacao=HOJE - timedelta(days=300)))
            s.commit()
        ev_a = c.post("/cadastro/eventos-sanitarios", json={"nome": "Vacina A", "categoria_preventiva": "vacina"}).json()
        ev_b = c.post("/cadastro/eventos-sanitarios", json={"nome": "Vacina B", "categoria_preventiva": "vacina"}).json()
        c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev_a["id"], "categoria_alvo": "Vacas", "produto": "Vacina A",
            "frequencia_valor": 12, "frequencia_unidade": "meses", "data_evento": (HOJE + timedelta(days=10)).isoformat(),
        })
        c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev_b["id"], "categoria_alvo": "Vacas", "produto": "Vacina B",
            "frequencia_valor": 12, "frequencia_unidade": "meses", "data_evento": (HOJE + timedelta(days=12)).isoformat(),
        })
        visao = _visao(c)
        # As duas ocorrências (10 e 12 dias, dentro da janela padrão de 7 dias
        # de agrupamento) devem cair na mesma janela, somando 1 + 11 = 12 animais
        # (>= mínimo padrão de 15? não — ajusta a expectativa ao padrão real).
        janela = next(j for j in visao["janelas"] if len(j["eventos"]) == 2)
        assert janela["animais_total"] == 12
        assert janela["sugerir_veterinario"] == (12 >= visao["min_animais_agrupamento"])
