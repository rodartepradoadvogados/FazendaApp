"""
GET /sanidade/ocorrencias e GET /sanidade/ocorrencias/{id} — Fase 2, telas 1
e 2 do redesenho do evento sanitário (docs/redesenho-evento-sanitario.md,
seções 3.2.1/3.2.2). Estado computado (provavel/em_edicao/confirmado/
realizado) e leitura de checklist/animais.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ChecklistTemplateItem

HOJE = date.today()

_TEMPLATE_VACINA = [
    (1, "estoque", "Estoque suficiente?"),
    (2, "vet", "Confirmação com o veterinário selecionado"),
    (3, "horario", "Horário da aplicação"),
    (4, "lotes", "Lotes de manejo atuais"),
    (5, "financeiro", "Lançamento financeiro"),
]


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

    with Session(engine) as s:
        for ordem, chave, nome in _TEMPLATE_VACINA:
            s.add(ChecklistTemplateItem(tipo="vacina", chave=chave, nome=nome, ordem=ordem, fazenda_id=None))
        s.commit()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _criar_regra(c, dias_ate_evento: int = 30) -> tuple[int, int]:
    r = c.post("/cadastro/eventos-sanitarios", json={
        "nome": "Vacina Brucelose", "tipo_agendamento": "evento", "gatilho": "novilha_apta",
        "gatilho_idade_meses": 3, "produto_padrao": "VACINA BRUCELOSE B19", "dose_padrao": 2, "unidade_padrao": "ml",
        "via_padrao": "Subcutânea",
    })
    assert r.status_code == 200, r.text
    evento_id = r.json()["id"]
    r = c.post("/sanidade/calendario", json={
        "evento_sanitario_id": evento_id, "categoria_alvo": "Novilhas 3 meses",
        "produto": "VACINA BRUCELOSE B19", "unidade": "ml", "dosagem": "2 ml",
        "frequencia_valor": 60, "frequencia_unidade": "dias",
        "data_evento": (HOJE + timedelta(days=dias_ate_evento)).isoformat(),
        "usa_cronograma": True,
    })
    assert r.status_code == 200, r.text
    return evento_id, r.json()["id"]


class TestListarOcorrencias:
    def test_regra_sem_cronograma_aparece_como_provavel(self, client):
        c, _ = client
        _criar_regra(c, dias_ate_evento=15)
        r = c.get("/sanidade/ocorrencias")
        assert r.status_code == 200, r.text
        linhas = r.json()["linhas"]
        assert len(linhas) == 1
        assert linhas[0]["estado"] == "provavel"
        assert linhas[0]["cronograma_id"] is None

    def test_carregar_agenda_materializa_e_aparece_como_provavel_com_cronograma(self, client):
        c, _ = client
        _criar_regra(c, dias_ate_evento=15)
        c.get("/agenda/", params={"data": HOJE.isoformat()})  # materializa o cronograma + checklist

        r = c.get("/sanidade/ocorrencias")
        linhas = r.json()["linhas"]
        assert linhas[0]["estado"] == "provavel"
        assert linhas[0]["cronograma_id"] is not None

    def test_indicador_vencidas_conta_atraso_nao_realizado(self, client):
        c, _ = client
        _criar_regra(c, dias_ate_evento=-10)  # já venceu
        c.get("/agenda/", params={"data": HOJE.isoformat()})
        r = c.get("/sanidade/ocorrencias")
        assert r.json()["indicadores"]["vencidas"] == 1


class TestDetalheOcorrencia:
    def test_detalhe_traz_checklist_materializado(self, client):
        c, _ = client
        _criar_regra(c, dias_ate_evento=15)
        c.get("/agenda/", params={"data": HOJE.isoformat()})
        cron_id = c.get("/sanidade/ocorrencias").json()["linhas"][0]["cronograma_id"]

        r = c.get(f"/sanidade/ocorrencias/{cron_id}")
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["estado"] == "provavel"
        assert [i["chave"] for i in dados["checklist"]] == ["estoque", "vet", "horario", "lotes", "financeiro"]
        assert all(i["status"] == "pendente" for i in dados["checklist"])

    def test_estado_avanca_para_em_edicao_ao_cumprir_um_item(self, client):
        c, _ = client
        _criar_regra(c, dias_ate_evento=15)
        c.get("/agenda/", params={"data": HOJE.isoformat()})
        cron_id = c.get("/sanidade/ocorrencias").json()["linhas"][0]["cronograma_id"]
        item_id = c.get(f"/sanidade/ocorrencias/{cron_id}").json()["checklist"][0]["id"]

        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_checklist_{item_id}"})
        dados = c.get(f"/sanidade/ocorrencias/{cron_id}").json()
        assert dados["estado"] == "em_edicao"

    def test_estado_confirmado_ao_completar_checklist(self, client):
        c, _ = client
        _criar_regra(c, dias_ate_evento=15)
        c.get("/agenda/", params={"data": HOJE.isoformat()})
        cron_id = c.get("/sanidade/ocorrencias").json()["linhas"][0]["cronograma_id"]
        itens = c.get(f"/sanidade/ocorrencias/{cron_id}").json()["checklist"]
        for item in itens:
            c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_checklist_{item['id']}", "acao": "pular"})

        dados = c.get(f"/sanidade/ocorrencias/{cron_id}").json()
        assert dados["estado"] == "confirmado"

    def test_estado_confirmado_via_desconsiderar(self, client):
        c, _ = client
        _criar_regra(c, dias_ate_evento=15)
        c.get("/agenda/", params={"data": HOJE.isoformat()})
        cron_id = c.get("/sanidade/ocorrencias").json()["linhas"][0]["cronograma_id"]

        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_desconsiderar_{cron_id}"})
        dados = c.get(f"/sanidade/ocorrencias/{cron_id}").json()
        assert dados["estado"] == "confirmado"
        assert dados["checklist_desconsiderado"] is True

    def test_ocorrencia_inexistente_da_404(self, client):
        c, _ = client
        r = c.get("/sanidade/ocorrencias/999999")
        assert r.status_code == 404
