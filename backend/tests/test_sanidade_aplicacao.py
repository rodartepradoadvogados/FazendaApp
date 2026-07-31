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
        # Baixa é POR ANIMAL (não uma agregada pro lote inteiro) — ver
        # test_lote_gera_um_movimento_por_animal_rastreavel_individualmente,
        # que confere o motivo (exclusão individual dentro de um lote).
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101", "102"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        r = client.get("/estoque/movimentos")
        movimentos = [m for m in r.json()["movimentos"] if m["nome_item"] == "Borgal 50ml"]
        assert len(movimentos) == 2  # um por animal, não um agregado do lote
        assert all(m["movimento"] == "Aplicação" for m in movimentos)
        assert all(m["quantidade"] == 10 for m in movimentos)
        assert sum(m["quantidade"] for m in movimentos) == 20  # 10ml * 2 animais — mesmo total de antes

    def test_lote_gera_um_movimento_por_animal_rastreavel_individualmente(self, client):
        """Regressão do risco documentado: lançar sanidade em lote (N animais,
        mesmo produto) baixava tudo numa única MovimentoEstoque presa ao id
        do ÚLTIMO animal — excluir a aplicação de qualquer um dos outros N-1
        não achava o que estornar (o estorno genérico de /exclusoes busca por
        origem_id). Agora cada animal tem sua própria movimentação, e excluir
        um deles reverte só a dose DELE, deixando os outros intactos."""
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101", "102", "103"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 10, "unidade": "ml"}],
        })
        sanidade_ids = r.json()["sanidade_ids"]
        assert len(sanidade_ids) == 3

        saldo_antes = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")["quantidade"]
        assert saldo_antes == 970  # 1000 - 10*3

        # Exclui só a aplicação do animal do MEIO do lote (não a última) pelo
        # fluxo central e auditado de exclusão — é ali que o bug se manifestava.
        r = client.post("/exclusoes/confirmar", json={"tipo": "sanidade", "id": str(sanidade_ids[1])})
        assert r.status_code == 200
        assert r.json()["avisos"] == []  # achou e reverteu sem aviso de "não encontrado"

        saldo_depois = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")["quantidade"]
        assert saldo_depois == 980  # devolveu só os 10ml deste animal — 970 + 10

        aplicacoes_restantes = client.get("/sanidade/aplicacoes").json()["aplicacoes"]
        assert len(aplicacoes_restantes) == 2
        assert sanidade_ids[1] not in [a["id"] for a in aplicacoes_restantes]


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


class TestPreventivoFalhaExplicita:
    """Antes, evento sem produto/dose/unidade padrão fazia a aplicação ser
    pulada em silêncio (200 com aplicacao: null, nada gravado/baixado). Agora
    é 400 explícito — só quando aplicar=True e há animais marcados."""

    def _criar_evento_sem_padrao(self, client) -> int:
        r = client.post("/cadastro/eventos-sanitarios", json={
            "nome": "Vermífugo", "categoria_preventiva": "vermifugacao",
        })
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_aplicar_sem_produto_padrao_da_400_citando_o_que_falta(self, client):
        from datetime import date
        ev_id = self._criar_evento_sem_padrao(client)
        r = client.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "aplicar": True,
        })
        assert r.status_code == 400, r.text
        detalhe = r.json()["detail"]
        assert "medicamento" in detalhe and "dose" in detalhe and "unidade" in detalhe
        assert "Vermífugo" in detalhe
        # Nada foi gravado (nem a regra do calendário, nem a aplicação).
        assert client.get("/sanidade/aplicacoes").json()["total"] == 0
        assert client.get("/sanidade/calendario").json() == []

    def test_produto_dose_unidade_informados_no_request_grava_e_baixa(self, client):
        from datetime import date
        ev_id = self._criar_evento_sem_padrao(client)
        r = client.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "aplicar": True, "produto": "Vacina X", "dose": 3, "unidade": "unidade",
        })
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"]["programado"] is False
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Vacina X")
        assert item["quantidade"] == 17  # 20 - 3

    def test_aplicar_falso_nao_exige_produto_e_so_grava_regra(self, client):
        """Regressão: aplicar=False continua só cadastrando/atualizando a regra
        do calendário, mesmo sem produto/dose/unidade — não deve dar erro."""
        from datetime import date
        ev_id = self._criar_evento_sem_padrao(client)
        r = client.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": ["101"],
            "aplicar": False,
        })
        assert r.status_code == 200, r.text
        assert r.json()["aplicacao"] is None
        assert r.json()["regra"] is not None
        assert client.get("/sanidade/aplicacoes").json()["total"] == 0

    def test_sem_animais_nao_exige_produto(self, client):
        """Cadastro só da regra (sem animal marcado) também não deve exigir
        produto padrão, mesmo com aplicar=True."""
        from datetime import date
        ev_id = self._criar_evento_sem_padrao(client)
        r = client.post("/sanidade/calendario/cadastrar-preventivo", json={
            "evento_sanitario_id": ev_id, "data_evento": date.today().isoformat(), "animais": [],
            "aplicar": True,
        })
        assert r.status_code == 200, r.text


class TestAvisoSaldoNegativo:
    def test_baixa_alem_do_saldo_avisa_e_baixa_mesmo_assim(self, client):
        r = client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": "Borgal 50ml", "quantidade": 1500, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        avisos = r.json()["avisos"]
        assert len(avisos) == 1
        assert "negativo" in avisos[0] and "Borgal 50ml" in avisos[0]
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == -500  # 1000 - 1500, a baixa acontece de qualquer forma


class TestEstornoEdicaoExclusao:
    def _criar(self, client, produto="Borgal 50ml", dose=10, unidade="ml"):
        client.post("/sanidade/aplicacoes", json={
            "data_aplicacao": "2026-07-08", "animais": ["101"],
            "itens": [{"produto": produto, "quantidade": dose, "unidade": unidade}],
        })
        return client.get("/sanidade/aplicacoes").json()["aplicacoes"][0]["id"]

    def test_editar_dose_ajusta_estoque_pela_diferenca(self, client):
        aid = self._criar(client, dose=10)
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 990  # 1000 - 10

        r = client.put(f"/sanidade/aplicacoes/{aid}", json={"dose": 30})
        assert r.status_code == 200, r.text
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 970  # 1000 - 30 (estorna 10, baixa 30)

    def test_excluir_devolve_quantidade_ao_estoque(self, client):
        aid = self._criar(client, dose=10)
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 990

        r = client.delete(f"/sanidade/aplicacoes/{aid}")
        assert r.status_code == 200, r.text
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Borgal 50ml")
        assert item["quantidade"] == 1000  # devolvido

    def test_excluir_item_nunca_baixado_nao_cria_estoque_fantasma(self, client):
        # "Serviço veterinário" é estocavel=False — nunca deu baixa ao ser
        # aplicado (ver test_item_nao_estocavel_nao_da_baixa).
        aid = self._criar(client, produto="Serviço veterinário", dose=1, unidade="unidade")
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Serviço veterinário")
        assert item["quantidade"] == 0

        r = client.delete(f"/sanidade/aplicacoes/{aid}")
        assert r.status_code == 200, r.text
        item = next(i for i in client.get("/estoque/").json()["itens"] if i["nome"] == "Serviço veterinário")
        assert item["quantidade"] == 0  # continua 0, não virou 1
