"""
Testes de lançamento de sanidade: múltiplos produtos por aplicação e
compatibilidade de unidade com a baixa de estoque.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Estoque


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
            s.add(Estoque(nome="Borgal 50ml", quantidade=1000, unidade="ml"))
            s.add(Estoque(nome="Vacina X", quantidade=20, unidade="unidade"))
            s.add(Estoque(nome="Serviço veterinário", quantidade=0, unidade="unidade", estocavel=False))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestUnidadesCompativeis:
    def test_ml_aceita_ml_unidade_dose_nao_litro(self, client):
        r = client.get("/sanidade/unidades-compativeis", params={"produto": "Borgal 50ml"})
        assert set(r.json()) == {"ml", "unidade", "dose"}
        assert "L" not in r.json()

    def test_produto_sem_estoque_libera_tudo(self, client):
        r = client.get("/sanidade/unidades-compativeis", params={"produto": "Não cadastrado"})
        assert "ml" in r.json() and "L" in r.json()


class TestRegistrarAplicacao:
    def test_multiplos_produtos_um_animal(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [
                {"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"},
                {"produto": "Vacina X", "quantidade": 1, "unidade": "unidade"},
            ],
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 2

    def test_um_produto_varios_animais_do_lote(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101", "102", "103"],
            "itens": [{"produto": "Vacina X", "quantidade": 1, "unidade": "unidade"}],
        })
        assert r.json()["criados"] == 3

    def test_unidade_compativel_da_baixa_direta(self, client):
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101", "102"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        r = client.get("/estoque/")
        item = next(i for i in r.json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 980  # 1000 - 10*2

    def test_unidade_incompativel_da_400(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 1, "unidade": "L"}],
        })
        assert r.status_code == 400

    def test_unidade_compativel_mas_diferente_da_estoque_avisa_sem_baixar(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 1, "unidade": "unidade"}],
        })
        assert r.status_code == 200
        assert len(r.json()["avisos"]) == 1
        estoque = client.get("/estoque/").json()["itens"]
        item = next(i for i in estoque if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 1000  # não deu baixa

    def test_sem_animais_da_400(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": [],
            "itens": [{"produto": "Vacina X", "quantidade": 1, "unidade": "unidade"}],
        })
        assert r.status_code == 400

    def test_sem_itens_da_400(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"], "itens": [],
        })
        assert r.status_code == 400

    def test_item_nao_estocavel_nao_da_baixa(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Serviço veterinário", "quantidade": 1, "unidade": "unidade"}],
        })
        assert r.status_code == 200
        assert r.json()["avisos"] == []
        estoque = client.get("/estoque/").json()["itens"]
        item = next(i for i in estoque if i["nome"] == "Serviço veterinário")
        assert item["quantidade"] == 0

    def test_lista_traz_id_para_editar_excluir(self, client):
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Vacina X", "quantidade": 1, "unidade": "unidade"}],
        })
        aplic = client.get("/sanidade/aplicacoes").json()["aplicacoes"]
        assert len(aplic) == 1
        assert isinstance(aplic[0]["id"], int)

    def test_baixa_direta_gera_movimento_de_estoque(self, client):
        # Antes, a baixa direta mexia em Estoque.quantidade sem deixar rastro
        # em MovimentoEstoque — ficava invisível no histórico/RMCA físico.
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101", "102"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        r = client.get("/estoque/movimentos")
        movimentos = [m for m in r.json()["movimentos"] if m["nome_item"] == "Borgal 50ml"]
        assert len(movimentos) == 1
        assert movimentos[0]["movimento"] == "Aplicação"
        assert movimentos[0]["quantidade"] == 20  # 10ml * 2 animais


class TestEditarExcluirAplicacao:
    def _criar(self, client):
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Vacina X", "quantidade": 1, "unidade": "unidade"}],
        })
        return client.get("/sanidade/aplicacoes").json()["aplicacoes"][0]["id"]

    def test_editar_produto_e_dose(self, client):
        aid = self._criar(client)
        r = client.put(f"/sanidade/aplicacoes/{aid}", json={"produto": "Vacina Y", "dose": 2})
        assert r.status_code == 200, r.text
        aplic = client.get("/sanidade/aplicacoes").json()["aplicacoes"][0]
        assert aplic["produto"] == "Vacina Y"
        assert aplic["dose"] == 2

    def test_editar_unidade_incompativel_da_400(self, client):
        # Cria com Borgal (estoque em ml) para haver checagem de compatibilidade.
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        aid = client.get("/sanidade/aplicacoes").json()["aplicacoes"][0]["id"]
        r = client.put(f"/sanidade/aplicacoes/{aid}", json={"unidade": "L"})
        assert r.status_code == 400

    def test_editar_inexistente_da_404(self, client):
        r = client.put("/sanidade/aplicacoes/99999", json={"produto": "X"})
        assert r.status_code == 404

    def test_excluir_aplicacao(self, client):
        aid = self._criar(client)
        r = client.delete(f"/sanidade/aplicacoes/{aid}")
        assert r.status_code == 200
        assert client.get("/sanidade/aplicacoes").json()["total"] == 0

    def test_excluir_inexistente_da_404(self, client):
        r = client.delete("/sanidade/aplicacoes/99999")
        assert r.status_code == 404


class TestAplicadoSimNao:
    """'Aplicado? não' ou data futura → não baixa estoque, fica programado na
    Agenda; dar baixa depois materializa a aplicação e baixa o estoque."""

    def test_futuro_nao_baixa_estoque_e_fica_programado(self, client):
        from datetime import date, timedelta
        futuro = (date.today() + timedelta(days=5)).isoformat()
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": futuro, "animais": ["101"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        assert r.status_code == 200
        assert r.json()["programado"] is True
        # Estoque intacto.
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 1000
        # Não entrou na lista de aplicações (só materializa quando aplicado).
        assert client.get("/sanidade/aplicacoes").json()["total"] == 0

    def test_aplicado_nao_hoje_fica_programado_e_baixa_ao_confirmar(self, client):
        from datetime import date
        hoje = date.today().isoformat()
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": hoje, "animais": ["101"], "aplicado": False,
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        assert r.json()["programado"] is True
        eventos = client.get("/agenda/", params={"data": hoje}).json()["eventos"]
        alvo = next(e for e in eventos if e["id"].startswith("aplic_agendada_"))
        assert alvo["produto"] == "Borgal 50ml"
        # Dar baixa → materializa + baixa estoque.
        client.post("/agenda/realizados", json={"evento_id": alvo["id"]})
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 990  # baixou 10
        assert client.get("/sanidade/aplicacoes").json()["total"] == 1

    def test_aplicado_hoje_baixa_na_hora(self, client):
        from datetime import date
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": date.today().isoformat(), "animais": ["101"], "aplicado": True,
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        assert r.json()["programado"] is False
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 990


class TestPreventivoAplicadoSimNao:
    """Mesmo toggle 'aplicado? sim/não' do lançamento avulso, agora também no
    fluxo de Preventivo/calendário sanitário (cadastrar-preventivo) — se não
    aplicado, vira pendência (AplicacaoAgendada) em vez de Sanidade real."""

    def _criar_evento(self, client) -> int:
        r = client.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vacina Aftosa", "categoria_preventiva": "vacina",
            "produto_padrao": "Vacina X", "dose_padrao": 2, "unidade_padrao": "unidade", "via_padrao": "IM",
        })
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_preventivo_nao_aplicado_nao_baixa_e_vira_pendencia(self, client):
        from datetime import date
        ev_id = self._criar_evento(client)
        r = client.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "aplicar": True, "aplicado": False,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["aplicacao"]["programado"] is True
        # Estoque intacto — nada foi baixado.
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Vacina X")
        assert item["quantidade"] == 20
        assert client.get("/sanidade/aplicacoes").json()["total"] == 0

    def test_preventivo_aplicado_baixa_na_hora(self, client):
        from datetime import date
        ev_id = self._criar_evento(client)
        r = client.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "aplicar": True, "aplicado": True,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["aplicacao"]["programado"] is False
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Vacina X")
        assert item["quantidade"] == 18  # baixou 2
        assert client.get("/sanidade/aplicacoes").json()["total"] == 1

    def test_preventivo_aplicado_default_true_retrocompativel(self, client):
        """Sem enviar 'aplicado' no payload (clientes antigos), comportamento
        continua sendo aplicar de verdade — igual a antes desta feature."""
        from datetime import date
        ev_id = self._criar_evento(client)
        r = client.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"], "aplicar": True,
        })
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"]["programado"] is False
