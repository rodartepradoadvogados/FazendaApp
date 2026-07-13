"""
Evento sanitário agendado (por época e por evento de vida) → aparece na Agenda
com o medicamento padrão; a baixa some quando a aplicação é registrada.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, MovimentoLote, Sanidade


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


def _agenda_sanidade(c) -> list[dict]:
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    return [e for e in r.json()["eventos"] if e.get("tipo") == "evento_sanitario"]


class TestCadastroRico:
    def test_cria_evento_epoca_com_medicamento_padrao(self, client):
        c, _ = client
        r = c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vermífugo do rebanho", "tipo_agendamento": "epoca",
            "data_primeiro": HOJE.isoformat(), "frequencia_valor": 6, "frequencia_unidade": "meses",
            "categoria_alvo": "Bezerras", "produto_padrao": "Ivermectina", "dose_padrao": 5, "unidade_padrao": "ml", "via_padrao": "Subcutânea",
        })
        assert r.status_code == 200, r.text
        assert r.json()["proxima_ocorrencia"] is not None

    def test_epoca_sem_data_da_400(self, client):
        c, _ = client
        r = c.post("/cadastro/eventos-sanitarios", json={"nome": "X", "tipo_agendamento": "epoca", "frequencia_valor": 6, "frequencia_unidade": "meses"})
        assert r.status_code == 400

    def test_nome_simples_ainda_funciona(self, client):
        c, _ = client
        r = c.post("/cadastro/eventos-sanitarios", json={"nome": "Brucelose B19"})
        assert r.status_code == 200, r.text
        assert r.json()["tipo_agendamento"] == "nenhum"


class TestAgendaEpoca:
    def test_epoca_aparece_na_agenda_com_produto(self, client):
        c, _ = client
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vermífugo", "tipo_agendamento": "epoca",
            "data_primeiro": HOJE.isoformat(), "frequencia_valor": 6, "frequencia_unidade": "meses",
            "produto_padrao": "Ivermectina", "dose_padrao": 5, "unidade_padrao": "ml",
        })
        eventos = _agenda_sanidade(c)
        assert any(e["produto"] == "Ivermectina" and e["data"] == HOJE.isoformat() for e in eventos)


class TestAgendaPorEvento:
    def test_nascimento_gera_evento_por_animal(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="401", data_nasc=HOJE - timedelta(days=10), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina ao nascer", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "produto_padrao": "VacinaX", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        eventos = _agenda_sanidade(c)
        meus = [e for e in eventos if e["numero_animal"] == "401"]
        assert len(meus) == 1
        assert meus[0]["produto"] == "VacinaX"

    def test_some_depois_de_aplicado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="402", data_nasc=HOJE - timedelta(days=5), sexo="F"))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina ao nascer", "tipo_agendamento": "evento", "gatilho": "nascimento",
            "produto_padrao": "VacinaX", "dose_padrao": 2, "unidade_padrao": "ml",
        })
        assert any(e["numero_animal"] == "402" for e in _agenda_sanidade(c))
        # Aplica → some da agenda (dedup por produto após o gatilho).
        with Session(engine) as s:
            s.add(Sanidade(numero_matriz="402", data_aplicacao=HOJE, produto="VacinaX", dose=2, unidade="ml"))
            s.commit()
        assert not any(e["numero_animal"] == "402" for e in _agenda_sanidade(c))

    def test_entrada_lote_gera_evento(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="500", data_nasc=HOJE - timedelta(days=800), sexo="F"))
            s.add(MovimentoLote(numero_matriz="500", lote_destino="PRE_PARTO", data_movimento=HOJE - timedelta(days=3)))
            s.commit()
        c.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina pré-parto", "tipo_agendamento": "evento", "gatilho": "entrada_lote", "gatilho_lote": "PRE_PARTO",
            "produto_padrao": "VacinaPre", "dose_padrao": 5, "unidade_padrao": "ml",
        })
        meus = [e for e in _agenda_sanidade(c) if e["numero_animal"] == "500"]
        assert len(meus) == 1 and meus[0]["produto"] == "VacinaPre"


def _agenda_calendario(c) -> list[dict]:
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    return [e for e in r.json()["eventos"] if e.get("tipo") == "calendario_sanitario"]


class TestCalendarioNaAgenda:
    """Regra do calendário sanitário (preventivo) precisa virar pendência na
    Agenda — antes só existia na tela de calendário e nunca dava baixa."""

    def _cria_exame(self, c, realizado=False):
        ev = c.post("/cadastro/eventos-sanitarios", json={"nome": "Exame de brucelose", "categoria_preventiva": "exame"})
        assert ev.status_code == 200, ev.text
        r = c.post("/sanidade/calendario", json={
            "evento_sanitario_id": ev.json()["id"], "categoria_alvo": "Novilhas",
            "frequencia_valor": 1, "frequencia_unidade": "anos", "data_evento": HOJE.isoformat(),
            "veterinario": "Dr. Carlos", "realizado": realizado,
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_exame_hoje_aparece_na_agenda(self, client):
        c, _ = client
        self._cria_exame(c)
        evs = _agenda_calendario(c)
        assert len(evs) == 1
        assert evs[0]["data"] == HOJE.isoformat()
        assert evs[0]["produto"] is None  # exame não tem baixa de estoque
        assert evs[0]["veterinario"] == "Dr. Carlos"
        assert evs[0]["categoria_preventiva"] == "exame"

    def test_baixa_some_da_agenda(self, client):
        c, _ = client
        self._cria_exame(c)
        eid = _agenda_calendario(c)[0]["id"]
        rb = c.post("/agenda/realizados", json={"evento_id": eid})
        assert rb.status_code == 200, rb.text
        assert not _agenda_calendario(c)

    def test_realizado_no_cadastro_ja_some(self, client):
        c, _ = client
        self._cria_exame(c, realizado=True)
        # marcado como realizado no cadastro → não aparece como pendência
        assert not _agenda_calendario(c)

    def test_excluir_regra_remove_da_agenda(self, client):
        c, _ = client
        regra = self._cria_exame(c)
        assert _agenda_calendario(c)
        rd = c.delete(f"/sanidade/calendario/{regra['id']}")
        assert rd.status_code == 200, rd.text
        assert not _agenda_calendario(c)
