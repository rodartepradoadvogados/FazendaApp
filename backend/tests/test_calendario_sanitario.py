"""Testes do Calendário sanitário: cálculo de recorrência e CRUD/listagem."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Doenca, EventoSanitario, PrincipioAtivo
from fazenda.rules.calendario_sanitario import proxima_ocorrencia


class TestProximaOcorrencia:
    def test_dias(self):
        assert proxima_ocorrencia(date(2026, 1, 1), 10, "dias") == date(2026, 1, 11)

    def test_meses(self):
        assert proxima_ocorrencia(date(2026, 1, 15), 4, "meses") == date(2026, 5, 15)

    def test_meses_com_estouro_de_ano(self):
        assert proxima_ocorrencia(date(2026, 11, 1), 3, "meses") == date(2027, 2, 1)

    def test_meses_com_fim_de_mes(self):
        # 31/jan + 1 mês não existe 31/fev — cai no último dia de fevereiro.
        assert proxima_ocorrencia(date(2026, 1, 31), 1, "meses") == date(2026, 2, 28)

    def test_anos(self):
        assert proxima_ocorrencia(date(2026, 3, 10), 1, "anos") == date(2027, 3, 10)

    def test_unidade_invalida(self):
        with pytest.raises(ValueError):
            proxima_ocorrencia(date(2026, 1, 1), 1, "semanas")


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
            s.add(EventoSanitario(nome="Vermífugo"))
            s.add(Doenca(nome="Verminose"))
            s.add(PrincipioAtivo(nome="Ivermectina"))
            s.commit()
        yield c, engine

    main.app.dependency_overrides.clear()


class TestCalendarioSanitarioCrud:
    def _regra(self, c, **overrides):
        dados = {
            "evento_sanitario_id": 1, "categoria_alvo": "Bezerras até Novilhas", "doenca_id": 1,
            "produto": "Ivermectina 4%", "principio_ativo_id": 1, "dosagem": "1 mL/50 kg",
            "frequencia_valor": 4, "frequencia_unidade": "meses", "data_evento": "2026-01-10",
        }
        dados.update(overrides)
        return c.post("/sanidade/calendario", json=dados)

    def test_cria_regra_e_calcula_proxima_ocorrencia(self, client):
        c, engine = client
        r = self._regra(c)
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["evento_sanitario_nome"] == "Vermífugo"
        assert corpo["doenca_nome"] == "Verminose"
        assert corpo["principio_ativo_nome"] == "Ivermectina"
        assert corpo["proxima_ocorrencia"] == "2026-05-10"

    def test_evento_sanitario_inexistente_da_400(self, client):
        c, engine = client
        r = self._regra(c, evento_sanitario_id=999)
        assert r.status_code == 400

    def test_frequencia_unidade_invalida_da_400(self, client):
        c, engine = client
        r = self._regra(c, frequencia_unidade="semanas")
        assert r.status_code == 400

    def test_frequencia_valor_zero_da_400(self, client):
        c, engine = client
        r = self._regra(c, frequencia_valor=0)
        assert r.status_code == 400

    def test_atualiza_regra(self, client):
        c, engine = client
        regra_id = self._regra(c).json()["id"]
        r = c.put(f"/sanidade/calendario/{regra_id}", json={
            "evento_sanitario_id": 1, "frequencia_valor": 6, "frequencia_unidade": "meses",
            "data_evento": "2026-01-10",
        })
        assert r.status_code == 200
        assert r.json()["proxima_ocorrencia"] == "2026-07-10"

    def test_regra_nova_sem_checklist_itens_no_body_nao_grava_customizacao(self, client):
        """Chamada antiga (sem passar pelo wizard novo, seção 3.7.0) — não
        manda `checklist_itens`, e a regra sai da lista com `checklist_itens: []`
        (usa o template do tipo dinamicamente, comportamento de sempre)."""
        c, engine = client
        r = self._regra(c)
        assert r.json()["checklist_itens"] == []

    def test_passo_4_do_wizard_grava_checklist_congelado_da_regra(self, client):
        c, engine = client
        r = self._regra(c, checklist_itens=[{"chave": "vet", "nome": "Confirmar vet", "ordem": 1}])
        assert r.status_code == 200
        assert r.json()["checklist_itens"] == [{"chave": "vet", "nome": "Confirmar vet", "ordem": 1}]

    def test_editar_regra_sem_checklist_itens_preserva_customizacao_anterior(self, client):
        c, engine = client
        regra_id = self._regra(c, checklist_itens=[{"chave": "vet", "nome": "Confirmar vet", "ordem": 1}]).json()["id"]
        r = c.put(f"/sanidade/calendario/{regra_id}", json={
            "evento_sanitario_id": 1, "frequencia_valor": 6, "frequencia_unidade": "meses", "data_evento": "2026-01-10",
        })
        assert r.json()["checklist_itens"] == [{"chave": "vet", "nome": "Confirmar vet", "ordem": 1}]

    def test_editar_regra_com_lista_vazia_remove_customizacao(self, client):
        c, engine = client
        regra_id = self._regra(c, checklist_itens=[{"chave": "vet", "nome": "Confirmar vet", "ordem": 1}]).json()["id"]
        r = c.put(f"/sanidade/calendario/{regra_id}", json={
            "evento_sanitario_id": 1, "frequencia_valor": 6, "frequencia_unidade": "meses", "data_evento": "2026-01-10",
            "checklist_itens": [],
        })
        assert r.json()["checklist_itens"] == []

    def test_lista_filtra_por_periodo_da_proxima_ocorrencia(self, client):
        c, engine = client
        self._regra(c, data_evento="2026-01-10", frequencia_valor=1, frequencia_unidade="meses")  # -> 2026-02-10
        self._regra(c, data_evento="2026-06-01", frequencia_valor=1, frequencia_unidade="meses")  # -> 2026-07-01

        r = c.get("/sanidade/calendario", params={"data_inicio": "2026-03-01", "data_fim": "2026-12-31"})
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["proxima_ocorrencia"] == "2026-07-01"

    def test_lista_filtra_por_evento(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(EventoSanitario(nome="Leptospirose"))
            s.commit()
        self._regra(c, evento_sanitario_id=1)
        self._regra(c, evento_sanitario_id=2)

        r = c.get("/sanidade/calendario", params={"evento_sanitario_id": 2})
        assert len(r.json()) == 1
        assert r.json()[0]["evento_sanitario_nome"] == "Leptospirose"
