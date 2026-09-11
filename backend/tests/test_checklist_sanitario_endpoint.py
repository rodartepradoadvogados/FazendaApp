"""
Endpoint do checklist da Ocorrência (Fase 1, passos 7-8 do redesenho do
evento sanitário) — POST /agenda/realizados com os prefixos
`cronograma_sanitario_checklist_` e `cronograma_sanitario_desconsiderar_`,
mesmo dispatch já usado por animal/modo/aplicar (ver test_cronograma_sanitario.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import CalendarioSanitario, ChecklistItem, ChecklistTemplateItem, CronogramaSanitario, EventoSanitario

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


def _criar_evento_e_calendario(c, dias_ate_evento: int = 30) -> tuple[int, int]:
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


def _agenda(c) -> list[dict]:
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()["eventos"]


def _itens_do_cronograma(engine, cronograma_id: int) -> list[ChecklistItem]:
    with Session(engine) as s:
        return s.exec(
            select(ChecklistItem).where(ChecklistItem.cronograma_id == cronograma_id).order_by(ChecklistItem.ordem)
        ).all()


class TestChecklistMaterializadoPelaAgenda:
    def test_carregar_a_agenda_materializa_o_checklist_da_ocorrencia(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        _agenda(c)  # dispara a criação do cronograma + materialização do checklist

        with Session(engine) as s:
            cron = s.exec(select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)).first()
        itens = _itens_do_cronograma(engine, cron.id)
        assert [i.chave for i in itens] == ["estoque", "vet", "horario", "lotes", "financeiro"]
        assert all(i.status == "pendente" for i in itens)


class TestEndpointChecklistItem:
    def test_confirmar_item_generico_estoque(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        _agenda(c)
        with Session(engine) as s:
            cron = s.exec(select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)).first()
        item = _itens_do_cronograma(engine, cron.id)[0]  # estoque

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_checklist_{item.id}"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            atualizado = s.get(ChecklistItem, item.id)
            assert atualizado.status == "cumprido"

    def test_pular_item_com_motivo(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        _agenda(c)
        with Session(engine) as s:
            cron = s.exec(select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)).first()
        item = _itens_do_cronograma(engine, cron.id)[0]

        r = c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_checklist_{item.id}", "acao": "pular", "motivo": "sem necessidade",
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            atualizado = s.get(ChecklistItem, item.id)
            assert atualizado.status == "pulado"
            assert atualizado.observacao == "sem necessidade"

    def test_item_vet_sim(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        _agenda(c)
        with Session(engine) as s:
            cron = s.exec(select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)).first()
        vet = next(i for i in _itens_do_cronograma(engine, cron.id) if i.chave == "vet")

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_checklist_{vet.id}", "resposta": "sim"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            atualizado = s.get(ChecklistItem, vet.id)
            assert atualizado.status == "cumprido"
            assert atualizado.resposta == "sim"

    def test_item_vet_nao_sem_justificativa_da_400(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        _agenda(c)
        with Session(engine) as s:
            cron = s.exec(select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)).first()
        vet = next(i for i in _itens_do_cronograma(engine, cron.id) if i.chave == "vet")

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_checklist_{vet.id}", "resposta": "nao"})
        assert r.status_code == 400

        r = c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_checklist_{vet.id}", "resposta": "nao", "motivo": "vacina vencida no estoque",
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            atualizado = s.get(ChecklistItem, vet.id)
            assert atualizado.status == "cumprido"  # não bloqueia
            assert atualizado.observacao == "vacina vencida no estoque"

    def test_item_horario_exige_valor(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        _agenda(c)
        with Session(engine) as s:
            cron = s.exec(select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)).first()
        horario = next(i for i in _itens_do_cronograma(engine, cron.id) if i.chave == "horario")

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_checklist_{horario.id}"})
        assert r.status_code == 400  # sem `resposta`

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_checklist_{horario.id}", "resposta": "09:30"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(ChecklistItem, horario.id).resposta == "09:30"

    def test_item_inexistente_da_404(self, client):
        """Mesmo helper `_exigir_da_fazenda` já usado por animal/modo/aplicar
        (agenda.py) — devolve 404 em vez de confirmar a existência do id.
        A trava de isolamento entre fazendas em si é do helper compartilhado,
        já coberta pelos testes dedicados de multi-tenant (test_isolamento_*/
        test_seguranca_*), não duplicada aqui."""
        c, _ = client
        _criar_evento_e_calendario(c)
        r = c.post("/agenda/realizados", json={"evento_id": "cronograma_sanitario_checklist_999999"})
        assert r.status_code == 404


class TestEndpointDesconsiderarCronograma:
    def test_desconsiderar_marca_flag_sem_tocar_itens(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        _agenda(c)
        with Session(engine) as s:
            cron = s.exec(select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)).first()

        r = c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_desconsiderar_{cron.id}", "motivo": "urgência do cliente",
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            atualizado = s.get(CronogramaSanitario, cron.id)
            assert atualizado.checklist_desconsiderado is True
            assert atualizado.checklist_desconsiderado_motivo == "urgência do cliente"
            # Nenhum item do checklist foi tocado.
            itens = _itens_do_cronograma(engine, cron.id)
            assert all(i.status == "pendente" for i in itens)

    def test_desconsiderar_bloqueado_apos_realizado(self, client):
        c, engine = client
        _, calendario_id = _criar_evento_e_calendario(c)
        _agenda(c)
        with Session(engine) as s:
            cron = s.exec(select(CronogramaSanitario).where(CronogramaSanitario.calendario_sanitario_id == calendario_id)).first()
            cron_id = cron.id
            cron.status = "concluido"
            s.add(cron)
            s.commit()

        r = c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_desconsiderar_{cron_id}"})
        assert r.status_code == 400
