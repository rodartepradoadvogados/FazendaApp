"""
Testes do lançamento de controle leiteiro (por vaca ou em lote, de uma vez).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ControleLeiteiro, Lactacao, Parto


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
            s.add(Animal(numero="101", grupo_primario="01 - Alta", raca="Girolando", del_dias=50, ativo=True))
            s.add(Animal(numero="102", grupo_primario="01 - Alta", raca="Holandês", del_dias=80, ativo=True))
            # POST /producao/controles passou a exigir uma `Lactacao` ABERTA na
            # data do controle (ver rules/lactacao.py) — antes a rota aceitava
            # qualquer animal, inclusive seco, novilha ou inexistente. O DEL
            # gravado no controle sai daqui, não mais de `Animal.del_dias`.
            s.add(Lactacao(numero_matriz="101", data_inicio=date(2026, 7, 8) - timedelta(days=50), origem="parto"))
            s.add(Lactacao(numero_matriz="102", data_inicio=date(2026, 7, 8) - timedelta(days=80), origem="parto"))
            s.commit()
        yield c

    main.app.dependency_overrides.clear()


class TestCriarControles:
    def test_lanca_uma_vaca(self, client):
        r = client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, 10.0]}],
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 1

    def test_lanca_lote_inteiro_de_uma_vez(self, client):
        r = client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [
                {"numero_matriz": "101", "ordenhas": [12.5, 10.0]},
                {"numero_matriz": "102", "ordenhas": [9.0, 8.0]},
            ],
        })
        assert r.status_code == 200
        assert r.json()["criados"] == 2

    def test_soma_as_ordenhas_e_herda_del_e_raca(self, client):
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, 10.0]}],
        })
        r = client.get("/producao/controles")
        registro = next(c for c in r.json()["controles"] if c["numero"] == "101")
        assert registro["producao_kg"] == 22.5
        assert registro["del"] == 50

    def test_pula_entradas_sem_nenhuma_ordenha(self, client):
        r = client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [
                {"numero_matriz": "101", "ordenhas": [12.5, 10.0]},
                {"numero_matriz": "102", "ordenhas": [0, 0]},
            ],
        })
        assert r.json()["criados"] == 1

    def test_persiste_ordenhas_individuais_e_grupo_atual(self, client):
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, 10.0]}],
        })
        r = client.get("/producao/controles")
        registro = next(c for c in r.json()["controles"] if c["numero"] == "101")
        assert registro["ordenha1_kg"] == 12.5
        assert registro["ordenha2_kg"] == 10.0
        assert registro["ordenha3_kg"] is None
        assert registro["grupo_primario"] == "01 - Alta"

    def test_reenviar_o_mesmo_animal_no_mesmo_dia_atualiza_em_vez_de_duplicar(self, client):
        """#68/#72 — reenvio (duplo clique, funcionário achando que não
        salvou) não pode duplicar a produção do dia; upsert por
        (numero_matriz, data_controle) em vez de inserir de novo."""
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, 10.0]}],
        })
        r2 = client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [15.0, 11.0]}],
        })
        assert r2.status_code == 200
        assert r2.json()["criados"] == 1

        r = client.get("/producao/controles")
        registros_101 = [c for c in r.json()["controles"] if c["numero"] == "101"]
        assert len(registros_101) == 1
        assert registros_101[0]["producao_kg"] == 26.0

    def test_persiste_terceira_ordenha(self, client):
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "102", "ordenhas": [8.0, 7.0, 3.0]}],
        })
        r = client.get("/producao/controles")
        registro = next(c for c in r.json()["controles"] if c["numero"] == "102")
        assert registro["ordenha3_kg"] == 3.0

    def test_ordenha_nao_lancada_fica_nula_e_nao_vira_zero(self, client):
        # Regressão: uma ordenha em branco (não lançada) deve ficar None, não
        # 0 — um 0 gravado como se fosse ordenha real puxaria a média de
        # manhã/noite do relatório para baixo silenciosamente.
        client.post("/producao/controles", json={
            "data_controle": "2026-07-08",
            "entradas": [{"numero_matriz": "101", "ordenhas": [12.5, None]}],
        })
        r = client.get("/producao/controles")
        registro = next(c for c in r.json()["controles"] if c["numero"] == "101")
        assert registro["ordenha1_kg"] == 12.5
        assert registro["ordenha2_kg"] is None
        assert registro["producao_kg"] == 12.5


@pytest.fixture
def client_com_dois_partos():
    """Vaca 201 com dois partos e três controles: um ANTES de qualquer parto
    conhecido, um DURANTE a 1ª lactação e um DURANTE a 2ª — grava direto no
    banco (não via POST) porque este teste é sobre a LEITURA de
    `GET /producao/controles`, não sobre o lançamento."""
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
            s.add(Animal(numero="201", grupo_primario="01 - Alta", raca="Holandês", ativo=True))
            s.add(Parto(numero_matriz="201", data_parto=date(2026, 1, 1), ordem_parto=1))
            s.add(Parto(numero_matriz="201", data_parto=date(2026, 7, 1), ordem_parto=2))
            s.add(ControleLeiteiro(numero_matriz="201", data_controle=date(2025, 1, 1), producao_kg=20.0))
            s.add(ControleLeiteiro(numero_matriz="201", data_controle=date(2026, 2, 1), producao_kg=25.0))
            s.add(ControleLeiteiro(numero_matriz="201", data_controle=date(2026, 8, 1), producao_kg=30.0))
            s.commit()
        yield c, engine
    main.app.dependency_overrides.clear()


class TestOrdemPartoNaListagem:
    """Regressão: GET /producao/controles rotulava TODOS os controles do
    animal com a contagem TOTAL de partos dele — uma vaca hoje de 2ª cria
    aparecia com "2" até nos controles de quando era primípara. Corrigido
    para calcular a ordem vigente NA DATA de cada controle (ver
    rules/ordem_parto_historica.py::ordem_parto_na_data), a mesma lógica já
    usada pelo relatório de Equivalente Maduro."""

    def test_ordem_muda_conforme_a_lactacao(self, client_com_dois_partos):
        c, engine = client_com_dois_partos
        r = c.get("/producao/controles")
        registros = {reg["data"]: reg["ordem_parto"] for reg in r.json()["controles"] if reg["numero"] == "201"}
        # Controle feito DURANTE a 1ª lactação: ordem 1, não 2 (a vaca só teve
        # o 2º parto depois) — é o bug clássico que este teste trava.
        assert registros["2026-02-01"] == 1
        # Controle feito DURANTE a 2ª lactação: ordem 2.
        assert registros["2026-08-01"] == 2

    def test_controle_anterior_ao_primeiro_parto_conhecido_fica_sem_ordem(self, client_com_dois_partos):
        # Nenhuma ordem inventada — nulo é mais honesto que um palpite que não
        # corresponde a nada (mesma filosofia de scripts/reconstruir_ordem_parto.py).
        c, engine = client_com_dois_partos
        r = c.get("/producao/controles")
        registro = next(reg for reg in r.json()["controles"] if reg["data"] == "2025-01-01")
        assert registro["ordem_parto"] is None


class TestRelatorioOrdemParto:
    """GET /producao/ordem-parto/divergencias — versão HTTP, somente leitura,
    do script scripts/reconstruir_ordem_parto.py (`levantar`/`gravar` foram
    portados para dentro do router — ver a seção "Reconstrução de
    ControleLeiteiro.ordem_parto" em fazenda/api/routers/producao.py). Testes
    focados no endpoint de ESCRITA (POST .../reconstruir) e no isolamento por
    fazenda ficam em test_ordem_parto_reconstrucao_endpoint.py."""

    def test_relatorio_reflete_o_mesmo_cenario_do_endpoint_de_listagem(self, client_com_dois_partos):
        c, engine = client_com_dois_partos
        r = c.get("/producao/ordem-parto/divergencias")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["partos"] == 2
        assert corpo["controles"] == 3
        # O atalho antigo é a contagem TOTAL de partos (2) aplicada aos 3
        # controles. A ordem correta por data é None, 1, 2 — o controle mais
        # recente (2026-08-01, já na 2ª lactação) bate com o atalho por
        # coincidência (é exatamente aí que o atalho SEMPRE acerta, porque a
        # contagem total É a ordem correta da lactação atual); os outros dois
        # divergem, que é o bug que a reconstrução existe pra corrigir.
        assert corpo["muda"] == 2
        # O controle anterior a qualquer parto conhecido não tem resposta
        # honesta — conta como "viraria desconhecido", não como um palpite.
        assert corpo["vira_desconhecido"] == 1

    def test_relatorio_nao_grava_nada(self, client_com_dois_partos):
        # Chamar a rota duas vezes não pode ter efeito colateral nenhum —
        # é leitura pura, igual ao script sem --gravar.
        c, engine = client_com_dois_partos
        c.get("/producao/ordem-parto/divergencias")
        r2 = c.get("/producao/ordem-parto/divergencias")
        assert r2.json()["muda"] == 2
        with Session(engine) as s:
            controles = s.exec(select(ControleLeiteiro)).all()
            assert all(ctrl.ordem_parto is None for ctrl in controles)
