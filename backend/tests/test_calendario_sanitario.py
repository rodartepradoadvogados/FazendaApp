"""Testes do Calendário sanitário: cálculo de recorrência e CRUD/listagem."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, Doenca, EventoSanitario, PrincipioAtivo
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
        assert corpo["proxima_ocorrencia_por_animal"] is False

    def test_regra_por_evento_de_vida_marca_proxima_ocorrencia_por_animal(self, client):
        """Bug relatado pelo usuário em 12/09/2026: uma regra por evento de
        vida (ex.: Brucelose B19, gatilho=nascimento) mostrava uma "próxima
        ocorrência" calculada pela fórmula periódica (data_evento + frequência)
        — valores vestigiais que o wizard nunca expõe nesse modo — divergindo
        da data real (por animal) mostrada em Ocorrências/Cronogramas.
        `proxima_ocorrencia_por_animal=True` avisa o frontend a não confiar
        nessa data como se fosse única."""
        c, engine = client
        with Session(engine) as s:
            s.add(EventoSanitario(nome="Brucelose B19", tipo_agendamento="evento", gatilho="nascimento"))
            s.commit()
        r = self._regra(c, evento_sanitario_id=2)
        assert r.status_code == 200
        assert r.json()["proxima_ocorrencia_por_animal"] is True

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

    def test_regra_com_cronograma_mostra_a_data_do_1o_ciclo_nao_data_evento_mais_frequencia(self, client):
        """Bug relatado pelo usuário em 12/09/2026 (verificação pós-merge):
        para uma regra com `usa_cronograma=True`, o motor do workflow
        (`cronograma_sanitario.cronograma_aberto`) trata `data_evento` como
        "a data da PRÓXIMA aplicação" ao criar o 1º cronograma — mas
        `proxima_ocorrencia` aqui sempre somava a frequência de novo por
        cima da mesma `data_evento`, tratando-a como "a da ÚLTIMA". As duas
        leituras da mesma regra divergiam por um ciclo inteiro, só no
        início (ex.: regra criada com data_evento=20/09 e frequência de 60
        dias mostrava "próxima ocorrência" = 19/11 em Regras cadastradas,
        enquanto Cronogramas/Calendário mostravam a data real, 20/09)."""
        c, engine = client
        r = self._regra(c, data_evento="2026-09-20", frequencia_valor=60, frequencia_unidade="dias", usa_cronograma=True)
        assert r.status_code == 200
        calendario_id = r.json()["id"]
        # Sem cronograma aberto ainda (Agenda nunca rodou pra esta regra) —
        # já usa a mesma data que `cronograma_aberto()` usaria ao criar o 1º.
        assert r.json()["proxima_ocorrencia"] == "2026-09-20"

        c.get("/agenda/", params={"data": "2026-09-12"})  # materializa o 1º cronograma
        regra = next(x for x in c.get("/sanidade/calendario").json() if x["id"] == calendario_id)
        assert regra["proxima_ocorrencia"] == "2026-09-20"

        cronograma_id = c.get("/sanidade/cronogramas", params={"calendario_id": calendario_id}).json()[0]["id"]
        with Session(engine) as s:
            s.add(Animal(numero="500", data_nasc=date(2020, 1, 1), sexo="F", ativo=True))
            s.commit()
        c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_incluir_manual_{cronograma_id}", "numero_matriz": "500",
        })
        c.post("/agenda/realizados", json={"evento_id": f"cronograma_sanitario_modo_{cronograma_id}", "modo": "propria"})
        r = c.post("/agenda/realizados", json={
            "evento_id": f"cronograma_sanitario_aplicar_{cronograma_id}",
            "produto": "Ivermectina 4%", "dose": 1, "unidade": "ml", "via": "Subcutânea",
        })
        assert r.status_code == 200, r.text
        c.get("/agenda/", params={"data": "2026-09-12"})  # materializa o 2º cronograma

        regra = next(x for x in c.get("/sanidade/calendario").json() if x["id"] == calendario_id)
        assert regra["proxima_ocorrencia"] == "2026-11-19"
        cronograma_2 = next(
            x for x in c.get("/sanidade/cronogramas", params={"calendario_id": calendario_id}).json() if x["status"] == "aberto"
        )
        assert cronograma_2["data_evento"] == "2026-11-19"
