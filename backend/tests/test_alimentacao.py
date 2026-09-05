"""
Testes da Alimentação: consumo por lote, necessidade mensal (com conversão
para sacos) e a baixa automática de estoque por dias decorridos (opção A),
incluindo a segurança contra baixa duplicada sob acesso concorrente.
"""
from __future__ import annotations

import json
import threading
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContratoFazenda, ContratoFazendaModulo
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.models import (
    AlimentacaoEstado, Alimento, AlimentoNutricional, AnaliseBromatologica, Animal, CategoriaAlimento,
    ConsumoAlimento, ControleLeiteiro, Dieta, DietaItemProgramado, DietaLancamento, DietaSimulacao,
    DietaSimulacaoItem, Estoque, Fazenda, IngredienteMS, Lote, MovimentoEstoque, TabelaNutricionalProduto,
)

HOJE = date(2026, 7, 8)


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # SQLite (StaticPool) expõe uma única conexão física real — diferente do
    # Postgres em produção, onde cada requisição tem sua própria conexão do
    # pool. Sem essa trava, threads concorrentes nos testes disputam a MESMA
    # conexão e corrompem o estado de transação uma da outra (falso positivo
    # de "race condition" que não existe em produção). A trava serializa só o
    # acesso à conexão compartilhada; a corrida entre requisições no endpoint
    # continua sendo exercida normalmente pelas 5 threads concorrentes.
    lock_conexao = threading.Lock()

    def _get_session_override():
        with lock_conexao, Session(engine) as session:
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


def _seed(engine):
    with Session(engine) as s:
        s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
        s.add(Animal(numero="2", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
        s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Silagem de milho", quantidade=20.0, unidade="kg"))
        s.add(Estoque(nome="Silagem de milho", categoria="alimento", quantidade=1000.0, unidade="kg"))
        # `modo_baixa_estoque="automatica"`: este seed alimenta os testes da
        # baixa por dias decorridos, então o lote precisa ter pedido esse
        # modo explicitamente — o padrão "consumo_real" não seria debitado
        # aqui (ver `_consumo_total_modo_automatica`).
        s.add(Lote(codigo="01", nome="Alta", modo_baixa_estoque="automatica"))
        s.commit()


class TestConsumo:
    def test_consumo_diario_cruza_dieta_com_efetivo(self, client):
        c, engine = client
        _seed(engine)
        r = c.get("/alimentacao/")
        assert r.status_code == 200
        total = {x["ingrediente"]: x["consumo_dia"] for x in r.json()["consumo_total"]}
        assert total["Silagem de milho"] == 40.0  # 20kg/cabeça * 2 animais


class TestNecessidadeMensal:
    def test_converte_para_sacos_quando_ensacado(self, client):
        c, engine = client
        _seed(engine)
        r_meta = c.put("/cadastro/estoque-itens/1", json={"unidade_embalagem": "Saca", "medida_embalagem": "kg/saca", "quantidade_embalagem": 25.0})
        assert r_meta.status_code == 200

        r = c.get("/alimentacao/necessidade-mensal")
        assert r.status_code == 200
        item = next(i for i in r.json()["itens"] if i["ingrediente"] == "Silagem de milho")
        assert item["necessidade_mes"] == 1200.0  # 40kg/dia * 30
        assert item["sacos_mes"] == 48  # 1200 / 25

    def test_deriva_sacos_da_unidade_saca_30kg_sem_precisar_do_cadastro_de_embalagem(self, client):
        """O item de estoque só tem `unidade="saca 30kg"` — o campo que quem
        cadastra o produto realmente preenche — sem preencher à parte o trio
        unidade_embalagem/medida_embalagem/quantidade_embalagem."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Animal(numero="2", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Ração", quantidade=5.0, unidade="kg"))
            s.add(Estoque(nome="Ração", categoria="alimento", quantidade=1000.0, unidade="saca 30kg"))
            s.commit()

        r = c.get("/alimentacao/necessidade-mensal")
        assert r.status_code == 200
        item = next(i for i in r.json()["itens"] if i["ingrediente"] == "Ração")
        assert item["necessidade_mes"] == 300.0  # 5kg/cabeça * 2 animais * 30
        assert item["ensacado"] is True
        assert item["kg_por_saco"] == 30.0
        assert item["sacos_mes"] == 10

    def test_cadastro_de_embalagem_tem_prioridade_sobre_a_unidade(self, client):
        """Se o trio de embalagem foi preenchido manualmente com um peso
        diferente do que a `unidade` sugere, o trio explícito vence."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Ração", quantidade=6.0, unidade="kg"))
            s.add(Estoque(nome="Ração", categoria="alimento", quantidade=1000.0, unidade="saca 30kg",
                          unidade_embalagem="Saca", medida_embalagem="kg/saca", quantidade_embalagem=25.0))
            s.commit()

        r = c.get("/alimentacao/necessidade-mensal")
        assert r.status_code == 200
        item = next(i for i in r.json()["itens"] if i["ingrediente"] == "Ração")
        assert item["necessidade_mes"] == 180.0  # 6kg/cabeça * 1 animal * 30
        assert item["kg_por_saco"] == 25.0
        assert item["sacos_mes"] == 8  # ceil(180 / 25)


class TestBaixaAutomatica:
    def test_primeira_chamada_so_estabelece_baseline_sem_baixar(self, client):
        c, engine = client
        _seed(engine)
        r = c.get("/alimentacao/")
        assert r.status_code == 200
        with Session(engine) as s:
            item = s.get(Estoque, 1)
            assert item.quantidade == 1000.0  # nada baixado ainda

    def test_primeiro_acesso_concorrente_nao_quebra(self, client):
        """
        Duas requisições batendo ao mesmo tempo no PRIMEIRO acesso (quando a
        linha de estado ainda não existe) não podem derrubar a requisição com
        um erro de integridade — a segunda perde a corrida de criação da linha
        e segue normalmente, sem tentar deduzir nada.
        """
        c, engine = client
        _seed(engine)
        resultados = []

        def _chamar():
            resultados.append(c.get("/alimentacao/"))

        threads = [threading.Thread(target=_chamar) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r.status_code == 200 for r in resultados)
        with Session(engine) as s:
            item = s.get(Estoque, 1)
            assert item.quantidade == 1000.0

    def test_baixa_proporcional_aos_dias_decorridos(self, client):
        c, engine = client
        _seed(engine)
        c.get("/alimentacao/")  # estabelece baseline = hoje
        with Session(engine) as s:
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=3)
            s.add(estado)
            s.commit()

        r = c.get("/alimentacao/")
        assert r.status_code == 200
        with Session(engine) as s:
            item = s.get(Estoque, 1)
            # 40kg/dia * 3 dias = 120kg baixados
            assert item.quantidade == 880.0
            movimentos = s.exec(MovimentoEstoque.__table__.select()).fetchall()
            assert len(movimentos) == 1

    def test_baixa_converte_kg_para_a_unidade_ensacada_do_item(self, client):
        """Item cadastrado como "saca 30kg" — a baixa precisa converter os kg
        consumidos para sacas antes de debitar, senão o saldo desaba ~30x mais
        rápido do que deveria (ver resolver_kg_por_unidade)."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Animal(numero="2", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Ração", quantidade=5.0, unidade="kg"))
            s.add(Estoque(nome="Ração", categoria="alimento", quantidade=1000.0, unidade="saca 30kg"))
            s.add(Lote(codigo="01", nome="Alta", modo_baixa_estoque="automatica"))
            s.commit()

        c.get("/alimentacao/")  # estabelece baseline = hoje
        with Session(engine) as s:
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=3)
            s.add(estado)
            s.commit()

        r = c.get("/alimentacao/")
        assert r.status_code == 200
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração")).first()
            # 5kg/cabeça * 2 animais * 3 dias = 30kg -> 30kg / 30kg/saca = 1 saca
            assert item.quantidade == 999.0

    def test_baixa_converte_kg_para_tonelada_via_quantidade_embalagem(self, client):
        """Mesmo bug do teste acima, mas para um item cadastrado em Tonelada
        (não "saca X kg" no texto de `unidade`) — só resolvido pelo trio
        unidade_embalagem/medida_embalagem/quantidade_embalagem, já que o
        texto "Tonelada (ton)" não bate no regex de saca. Antes deste fix,
        `resolver_kg_por_unidade` só reconhecia literalmente "Saca"/"kg/saca"
        e debitava os kg consumidos 1:1 como se fossem toneladas — erro de
        escala 1000x, reportado com um caso real de produção."""
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Animal(numero="2", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Caroço de algodão", quantidade=5.0, unidade="kg"))
            s.add(Estoque(
                nome="Caroço de algodão", categoria="alimento", quantidade=40.0, unidade="Tonelada (ton)",
                unidade_embalagem="Tonelada (ton)", medida_embalagem="kg/ton", quantidade_embalagem=1000,
            ))
            s.add(Lote(codigo="01", nome="Alta", modo_baixa_estoque="automatica"))
            s.commit()

        c.get("/alimentacao/")  # estabelece baseline = hoje
        with Session(engine) as s:
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=2)
            s.add(estado)
            s.commit()

        r = c.get("/alimentacao/")
        assert r.status_code == 200
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Caroço de algodão")).first()
            # 5kg/cabeça * 2 animais * 2 dias = 20kg -> 20kg / 1000kg-por-tonelada = 0,02 tonelada.
            # Com o bug, isso teria debitado 20 TONELADAS (item.quantidade == 20.0).
            assert item.quantidade == pytest.approx(39.98)

    def test_item_nao_estocavel_nao_sofre_baixa_automatica(self, client):
        c, engine = client
        _seed(engine)
        with Session(engine) as s:
            item = s.get(Estoque, 1)
            item.estocavel = False
            s.add(item)
            s.commit()

        c.get("/alimentacao/")
        with Session(engine) as s:
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=3)
            s.add(estado)
            s.commit()

        c.get("/alimentacao/")
        with Session(engine) as s:
            item = s.get(Estoque, 1)
            assert item.quantidade == 1000.0  # não estocável — sem baixa automática

    def test_segunda_chamada_no_mesmo_dia_nao_baixa_de_novo(self, client):
        c, engine = client
        _seed(engine)
        c.get("/alimentacao/")
        with Session(engine) as s:
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=2)
            s.add(estado)
            s.commit()

        c.get("/alimentacao/")
        r2 = c.get("/alimentacao/necessidade-mensal")
        assert r2.status_code == 200
        with Session(engine) as s:
            item = s.get(Estoque, 1)
            assert item.quantidade == 920.0  # só os 2 dias, não dobrou na segunda chamada

    def test_baixa_concorrente_nao_duplica(self, client):
        """
        Duas requisições concorrentes na mesma janela de dias decorridos devem
        resultar numa ÚNICA baixa — a trava otimista (compare-and-swap) garante
        que só uma delas de fato desconta o estoque.
        """
        c, engine = client
        _seed(engine)
        c.get("/alimentacao/")
        with Session(engine) as s:
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=5)
            s.add(estado)
            s.commit()

        resultados = []

        def _chamar():
            resultados.append(c.get("/alimentacao/"))

        threads = [threading.Thread(target=_chamar) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r.status_code == 200 for r in resultados)
        with Session(engine) as s:
            item = s.get(Estoque, 1)
            # 40kg/dia * 5 dias = 200kg — não 1000kg (o que aconteceria se as 5
            # requisições tivessem baixado cada uma por conta própria).
            assert item.quantidade == 800.0
            movimentos = s.exec(MovimentoEstoque.__table__.select()).fetchall()
            assert len(movimentos) == 1


class TestEstoquePreferidoResolucao:
    """Fase P1, Gap 3 — `Alimento.estoque_preferido_id` move o item
    escolhido para o INÍCIO da lista de candidatos de `_estoque_por_alimento`
    (nunca remove os outros), e todo call site que pega `candidatos[0]`
    passa a debitar/consumir esse item sem precisar mudar."""

    def _cenario(self, engine, modo_baixa_estoque: str | None = None):
        from fazenda.models import DietaItemProgramado, DietaLancamento

        with Session(engine) as s:
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            alimento = Alimento(nome="Farelo de soja")
            s.add(alimento)
            s.commit()
            s.refresh(alimento)
            e_a = Estoque(nome="Farelo de soja — Lote A", categoria="alimento",
                          quantidade=500.0, unidade="kg", alimento_id=alimento.id)
            e_b = Estoque(nome="Farelo de soja — Lote B", categoria="alimento",
                          quantidade=500.0, unidade="kg", alimento_id=alimento.id)
            s.add(e_a)
            s.add(e_b)
            # `Dieta` (CSV legado) alimenta a baixa automática; `DietaLancamento`
            # + `DietaItemProgramado` (lançamento) é o que o consumo MANUAL
            # exige pra não cair em "fora da dieta" (B4/B5) — os dois convivem.
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Farelo de soja", quantidade=10.0, unidade="kg"))
            dieta_lanc = DietaLancamento(lote=1, data_abertura=HOJE, base_quantidade="total")
            s.add(dieta_lanc)
            # Só cria o cadastro do lote quando o teste precisa de um modo
            # explícito (a baixa automática exige opt-in "automatica"); os
            # testes de consumo MANUAL não passam `modo_baixa_estoque` e
            # dependem do padrão restritivo "consumo_real" sem cadastro nenhum.
            if modo_baixa_estoque is not None:
                s.add(Lote(codigo="01", nome="Alta", modo_baixa_estoque=modo_baixa_estoque))
            s.commit()
            s.refresh(dieta_lanc)
            s.add(DietaItemProgramado(dieta_lancamento_id=dieta_lanc.id, alimento="Farelo de soja", quantidade=10.0, unidade="kg"))
            s.commit()
            s.refresh(e_a)
            s.refresh(e_b)
            return alimento.id, e_a.id, e_b.id

    def test_estoque_por_alimento_poe_o_preferido_na_frente(self, client):
        c, engine = client
        alimento_id, id_a, id_b = self._cenario(engine)
        with Session(engine) as s:
            alimento = s.get(Alimento, alimento_id)
            alimento.estoque_preferido_id = id_b
            s.add(alimento)
            s.commit()

            from fazenda.api.routers.alimentacao import _estoque_por_alimento
            por_alimento, _ = _estoque_por_alimento(s, None)
            candidatos = por_alimento["farelo de soja"]
            assert [c["id"] for c in candidatos] == [id_b, id_a]  # preferido primeiro
            assert {c["id"] for c in candidatos} == {id_a, id_b}  # nenhum candidato sumiu

    def test_estoque_por_alimento_preserva_ordem_de_hoje_sem_preferencia(self, client):
        """Não-regressão crítica do Gap 3: SEM `estoque_preferido_id` (o
        padrão), a ordem continua EXATAMENTE a que a query devolve hoje —
        mesma checagem dinâmica de TestEscolhaArbitrariaDeCandidato (T11) em
        test_migracao_alimento.py, que este teste espelha."""
        c, engine = client
        alimento_id, id_a, id_b = self._cenario(engine)
        with Session(engine) as s:
            query_ordem_crua = select(Estoque).where(Estoque.alimento_id.is_not(None)).order_by(Estoque.id)
            ordem_esperada = [e.id for e in s.exec(query_ordem_crua).all()]

            from fazenda.api.routers.alimentacao import _estoque_por_alimento
            por_alimento, _ = _estoque_por_alimento(s, None)
            candidatos = por_alimento["farelo de soja"]
            assert [c["id"] for c in candidatos] == ordem_esperada

    def test_baixa_automatica_debita_o_item_preferido(self, client):
        c, engine = client
        alimento_id, id_a, id_b = self._cenario(engine, modo_baixa_estoque="automatica")
        with Session(engine) as s:
            alimento = s.get(Alimento, alimento_id)
            alimento.estoque_preferido_id = id_b
            s.add(alimento)
            s.commit()

        c.get("/alimentacao/")  # baseline
        with Session(engine) as s:
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=1)
            s.add(estado)
            s.commit()

        r = c.get("/alimentacao/")
        assert r.status_code == 200
        with Session(engine) as s:
            item_a = s.get(Estoque, id_a)
            item_b = s.get(Estoque, id_b)
            assert item_b.quantidade == 490.0  # o preferido foi debitado
            assert item_a.quantidade == 500.0  # o outro nem foi tocado

    def test_resolver_estoque_item_consumo_manual_usa_o_preferido(self, client):
        c, engine = client
        alimento_id, id_a, id_b = self._cenario(engine)
        with Session(engine) as s:
            alimento = s.get(Alimento, alimento_id)
            alimento.estoque_preferido_id = id_a
            s.add(alimento)
            s.commit()

        r = c.post("/alimentacao/consumo", json={
            "lote": 1, "data": "2026-07-08", "origem": "kg",
            "itens": [{"alimento": "Farelo de soja", "quantidade": 10.0, "unidade": "kg"}],
        })
        assert r.status_code == 201
        with Session(engine) as s:
            item_a = s.get(Estoque, id_a)
            item_b = s.get(Estoque, id_b)
            assert item_a.quantidade == 490.0  # o preferido foi debitado
            assert item_b.quantidade == 500.0  # o outro nem foi tocado


class TestDietaLancamento:
    def _criar(self, c, **overrides):
        dados = {
            "lote": 1, "responsavel": "Alexandre Scarpa", "data_abertura": "2026-01-10",
            "data_prevista_encerramento": "2026-02-10",
            "itens": [{"alimento": "Silagem", "quantidade": 300.0, "unidade": "kg"}],
        }
        dados.update(overrides)
        return c.post("/alimentacao/dietas", json=dados)

    def test_cria_dieta_com_itens_programados(self, client):
        c, engine = client
        r = self._criar(c)
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["ativa"] is True
        assert corpo["itens_programados"][0]["alimento"] == "Silagem"
        assert corpo["itens_programados"][0]["quantidade"] == 300.0

    def test_sem_itens_da_400(self, client):
        c, engine = client
        r = self._criar(c, itens=[])
        assert r.status_code == 400

    def test_nao_permite_duas_dietas_ativas_no_mesmo_lote(self, client):
        c, engine = client
        self._criar(c)
        r = self._criar(c)
        assert r.status_code == 409

    def test_permite_nova_dieta_apos_encerrar_a_anterior(self, client):
        c, engine = client
        dieta_id = self._criar(c).json()["id"]
        c.put(f"/alimentacao/dietas/{dieta_id}/encerrar", json={"data_efetivo_encerramento": "2026-01-20"})
        r = self._criar(c)
        assert r.status_code == 201

    def test_encerrar_dieta_ja_encerrada_da_400(self, client):
        c, engine = client
        dieta_id = self._criar(c).json()["id"]
        c.put(f"/alimentacao/dietas/{dieta_id}/encerrar", json={"data_efetivo_encerramento": "2026-01-20"})
        r = c.put(f"/alimentacao/dietas/{dieta_id}/encerrar", json={"data_efetivo_encerramento": "2026-01-21"})
        assert r.status_code == 400

    def test_lista_filtra_por_lote_e_ativo(self, client):
        c, engine = client
        dieta_id = self._criar(c, lote=1).json()["id"]
        self._criar(c, lote=2)
        c.put(f"/alimentacao/dietas/{dieta_id}/encerrar", json={"data_efetivo_encerramento": "2026-01-20"})

        r = c.get("/alimentacao/dietas", params={"lote": 2})
        assert len(r.json()) == 1
        assert r.json()[0]["lote"] == 2

        r = c.get("/alimentacao/dietas", params={"ativo": False})
        assert len(r.json()) == 1
        assert r.json()[0]["lote"] == 1

    def test_registra_real_e_comparativo(self, client):
        c, engine = client
        dieta_id = self._criar(c).json()["id"]
        r = c.post(f"/alimentacao/dietas/{dieta_id}/real", json={
            "data": "2026-01-11", "itens": [{"alimento": "Silagem", "quantidade": 280.0, "unidade": "kg"}],
        })
        assert r.status_code == 201
        c.post(f"/alimentacao/dietas/{dieta_id}/real", json={
            "data": "2026-01-12", "itens": [{"alimento": "Silagem", "quantidade": 320.0, "unidade": "kg"}],
        })

        r = c.get(f"/alimentacao/dietas/{dieta_id}/comparativo")
        assert r.status_code == 200
        item = r.json()["itens"][0]
        assert item["alimento"] == "Silagem"
        assert item["programado"] == 300.0
        assert item["real_total"] == 600.0
        assert item["real_dias"] == 2
        assert item["real_media_dia"] == 300.0

    def test_dieta_inexistente_da_404_no_comparativo(self, client):
        c, engine = client
        r = c.get("/alimentacao/dietas/999/comparativo")
        assert r.status_code == 404

    def test_alimentos_padrao_traz_lista_fixa(self, client):
        c, engine = client
        r = c.get("/alimentacao/alimentos-padrao")
        assert r.status_code == 200
        assert "Silagem" in r.json()
        assert "Ração Bezerro 1" in r.json()


class TestAgendaDieta:
    def test_dieta_ativa_com_previsao_gera_evento_de_analise(self, client):
        c, engine = client
        dieta_id = c.post("/alimentacao/dietas", json={
            "lote": 3, "data_abertura": "2026-07-01", "data_prevista_encerramento": "2026-07-15",
            "itens": [{"alimento": "Ração Bezerro 1", "quantidade": 50.0, "unidade": "kg"}],
        }).json()["id"]

        r = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30})
        assert r.status_code == 200
        eventos = [e for e in r.json()["eventos"] if e["id"] == f"dieta_analise_{dieta_id}"]
        assert len(eventos) == 1
        assert eventos[0]["data"] == "2026-07-15"
        assert eventos[0]["categoria"] == "alimentacao"
        assert "lote 3" in eventos[0]["descricao"]

    def test_dieta_encerrada_nao_gera_evento(self, client):
        c, engine = client
        dieta_id = c.post("/alimentacao/dietas", json={
            "lote": 4, "data_abertura": "2026-07-01", "data_prevista_encerramento": "2026-07-15",
            "itens": [{"alimento": "Corte 21", "quantidade": 10.0, "unidade": "kg"}],
        }).json()["id"]
        c.put(f"/alimentacao/dietas/{dieta_id}/encerrar", json={"data_efetivo_encerramento": "2026-07-05"})

        r = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e["id"] == f"dieta_analise_{dieta_id}"]
        assert len(eventos) == 0

    def test_marcar_realizado_remove_evento_de_dieta(self, client):
        c, engine = client
        dieta_id = c.post("/alimentacao/dietas", json={
            "lote": 5, "data_abertura": "2026-07-01", "data_prevista_encerramento": "2026-07-15",
            "itens": [{"alimento": "Milk Proteico", "quantidade": 10.0, "unidade": "kg"}],
        }).json()["id"]

        c.post("/agenda/realizados", json={"evento_id": f"dieta_analise_{dieta_id}"})
        r = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30})
        eventos = [e for e in r.json()["eventos"] if e["id"] == f"dieta_analise_{dieta_id}"]
        assert len(eventos) == 0


class TestDietaContextoApresentacao:
    """Contexto do lote para o veterinário, apresentação para o funcionário e o
    fluxo de encerrar a dieta anterior ao salvar a nova (D3/D4)."""

    def _seed_lote(self, engine):
        # Lote 1 cadastrado (nome) + 2 vacas ativas com CL e DEL.
        with Session(engine) as s:
            s.add(Lote(codigo="01", nome="Alta Produção"))
            s.add(Animal(numero="10", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta",
                         ativo=True, del_dias=100, ult_cl_kg=32.0, data_ult_leite=date(2026, 7, 1)))
            s.add(Animal(numero="11", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta",
                         ativo=True, del_dias=200, ult_cl_kg=24.0, data_ult_leite=date(2026, 7, 1)))
            s.commit()

    def test_encerrar_anterior_encerra_na_data_da_nova(self, client):
        c, engine = client
        primeira = c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-01-10",
            "itens": [{"alimento": "Silagem", "quantidade": 300.0, "unidade": "kg"}],
        }).json()
        # Sem a flag → 409.
        r = c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-02-01",
            "itens": [{"alimento": "Silagem", "quantidade": 320.0, "unidade": "kg"}],
        })
        assert r.status_code == 409
        # Com a flag → 201 e encerra a anterior na data de início da nova.
        r = c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-02-01", "encerrar_anterior": True,
            "itens": [{"alimento": "Silagem", "quantidade": 320.0, "unidade": "kg"}],
        })
        assert r.status_code == 201
        dietas = c.get("/alimentacao/dietas", params={"lote": 1}).json()
        antiga = next(d for d in dietas if d["id"] == primeira["id"])
        assert antiga["ativa"] is False
        assert antiga["data_efetivo_encerramento"] == "2026-02-01"

    def test_contexto_do_lote(self, client):
        c, engine = client
        self._seed_lote(engine)
        c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-05",
            "itens": [{"alimento": "Silagem", "quantidade": 400.0, "unidade": "kg"}],
        })
        r = c.get("/alimentacao/dietas/contexto/1")
        assert r.status_code == 200
        ctx = r.json()
        assert ctx["nome"] == "Alta Produção"
        assert ctx["qtd_animais"] == 2
        assert ctx["del_medio"] == 150
        assert ctx["media_cl"] == 28.0
        assert ctx["data_ult_cl"] == "2026-07-01"
        # Ordenado por último CL desc: 32 antes de 24.
        assert [a["numero"] for a in ctx["animais"]] == ["10", "11"]
        # Última dieta: total/dia 400 → por cabeça 200.
        assert ctx["ultima_dieta"]["itens"][0]["total_dia"] == 400.0
        assert ctx["ultima_dieta"]["itens"][0]["por_cabeca"] == 200.0

    def test_contexto_reflete_controle_leiteiro_lancado_pelo_app_nao_o_campo_congelado(self, client):
        """Bug relatado: Animal.ult_cl_kg/data_ult_leite só é escrito pelo
        parser do GERAL.csv (aposentado) — lançar um controle leiteiro novo
        pelo próprio app (POST /producao/controles) não atualiza esses
        campos, então o contexto da dieta continuava mostrando a produção e
        a data do último CSV importado. Precisa refletir o controle mais
        recente de verdade (tabela controle_leiteiro)."""
        c, engine = client
        self._seed_lote(engine)
        with Session(engine) as s:
            # Controle leiteiro lançado pelo app, bem mais recente que o
            # campo congelado (2026-07-01) semeado em _seed_lote.
            s.add(ControleLeiteiro(numero_matriz="10", data_controle=date(2026, 8, 13), producao_kg=40.0))
            s.add(ControleLeiteiro(numero_matriz="11", data_controle=date(2026, 8, 13), producao_kg=30.0))
            s.commit()

        r = c.get("/alimentacao/dietas/contexto/1")
        assert r.status_code == 200
        ctx = r.json()
        # Média/data vêm do controle leiteiro AO VIVO (40+30)/2 = 35, não do
        # campo congelado (32+24)/2 = 28.
        assert ctx["media_cl"] == 35.0
        assert ctx["data_ult_cl"] == "2026-08-13"
        assert {a["numero"]: a["ult_cl_kg"] for a in ctx["animais"]} == {"10": 40.0, "11": 30.0}

    def test_contexto_cai_no_campo_congelado_so_para_quem_nao_tem_controle_ao_vivo(self, client):
        c, engine = client
        self._seed_lote(engine)
        with Session(engine) as s:
            # Só o animal 10 tem controle ao vivo — o 11 continua no fallback.
            s.add(ControleLeiteiro(numero_matriz="10", data_controle=date(2026, 8, 13), producao_kg=40.0))
            s.commit()

        r = c.get("/alimentacao/dietas/contexto/1").json()
        por_numero = {a["numero"]: a["ult_cl_kg"] for a in r["animais"]}
        assert por_numero["10"] == 40.0
        assert por_numero["11"] == 24.0  # fallback do campo congelado

    def test_apresentacao_para_o_funcionario(self, client):
        c, engine = client
        self._seed_lote(engine)
        dieta_id = c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-05",
            "itens": [{"alimento": "Silagem", "quantidade": 400.0, "unidade": "kg"}],
        }).json()["id"]
        r = c.get(f"/alimentacao/dietas/{dieta_id}/apresentacao")
        assert r.status_code == 200
        ap = r.json()
        assert ap["num_tratos"] == 2
        assert ap["qtd_animais"] == 2
        item = ap["itens"][0]
        assert item["total_dia"] == 400.0
        assert item["total_trato"] == 200.0
        assert item["por_cabeca"] == 200.0
        # Somatório de kg no vagão (só itens em kg).
        assert ap["vagao_kg_dia"] == 400.0
        assert ap["vagao_kg_trato"] == 200.0

    def test_apresentacao_e_contexto_respeitam_dieta_lancada_por_animal(self, client):
        """Bug pré-existente (spec): `apresentacao_dieta` e o bloco
        `ultima_dieta.itens` de `contexto_dieta` ignoravam `base_quantidade`
        da dieta e tratavam `quantidade` como sempre sendo o total do lote.
        Lote com 2 animais, dieta lançada "por animal" com 2kg/cabeça/dia — o
        total do lote tem que dar 4kg (não 2kg, e não 0.2kg de dobrar a
        divisão), e por_cabeca tem que continuar 2kg (não 1kg)."""
        c, engine = client
        self._seed_lote(engine)
        dieta_id = c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-05", "base_quantidade": "animal",
            "itens": [{"alimento": "Concentrado", "quantidade": 2.0, "unidade": "kg"}],
        }).json()["id"]

        ap = c.get(f"/alimentacao/dietas/{dieta_id}/apresentacao").json()
        item = ap["itens"][0]
        assert item["total_dia"] == 4.0
        assert item["por_cabeca"] == 2.0
        assert item["total_trato"] == 2.0
        assert ap["vagao_kg_dia"] == 4.0
        assert ap["vagao_kg_trato"] == 2.0

        ctx = c.get("/alimentacao/dietas/contexto/1").json()
        item_ctx = ctx["ultima_dieta"]["itens"][0]
        assert item_ctx["total_dia"] == 4.0
        assert item_ctx["por_cabeca"] == 2.0

    def test_apresentacao_mistura_base_por_item_na_mesma_dieta(self, client):
        """O pedido do proprietário: dentro da MESMA dieta/lote, um item pode
        ser lançado em total do lote e outro por cabeça — cada um calcula
        pela SUA PRÓPRIA base, independente do padrão da dieta. Dieta padrão
        "total"; Silagem sem override (herda "total", 400kg do lote);
        Concentrado com override "animal" (3kg/cabeça, lote de 2 animais)."""
        c, engine = client
        self._seed_lote(engine)
        dieta_id = c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-05", "base_quantidade": "total",
            "itens": [
                {"alimento": "Silagem", "quantidade": 400.0, "unidade": "kg"},
                {"alimento": "Concentrado", "quantidade": 3.0, "unidade": "kg", "base_quantidade": "animal"},
            ],
        }).json()["id"]

        ap = c.get(f"/alimentacao/dietas/{dieta_id}/apresentacao").json()
        por_alimento = {it["alimento"]: it for it in ap["itens"]}
        assert por_alimento["Silagem"]["total_dia"] == 400.0
        assert por_alimento["Silagem"]["por_cabeca"] == 200.0
        assert por_alimento["Concentrado"]["total_dia"] == 6.0
        assert por_alimento["Concentrado"]["por_cabeca"] == 3.0
        # Vagão soma o total do LOTE de cada item na sua própria base: 400 + 6.
        assert ap["vagao_kg_dia"] == 406.0

    def test_nova_dieta_gera_alerta_vespera_e_dia(self, client):
        c, engine = client
        self._seed_lote(engine)
        # Dieta que começa em 2026-07-09 → na agenda de 08 sai "para AMANHÃ",
        # na de 09 sai "HOJE".
        dieta_id = c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-09",
            "itens": [{"alimento": "Silagem", "quantidade": 400.0, "unidade": "kg"}],
        }).json()["id"]

        r = c.get("/agenda/", params={"data": "2026-07-08", "dias": 30})
        vespera = [e for e in r.json()["eventos"] if e.get("tipo") == "nova_dieta"]
        assert len(vespera) == 1
        assert "AMANHÃ" in vespera[0]["descricao"]
        assert vespera[0]["ref"] == str(dieta_id)

        r = c.get("/agenda/", params={"data": "2026-07-09", "dias": 30})
        hoje_alerta = [e for e in r.json()["eventos"] if e.get("tipo") == "nova_dieta"]
        assert len(hoje_alerta) == 1
        assert "HOJE" in hoje_alerta[0]["descricao"]

    def test_alerta_de_nova_dieta_e_um_comunicado_nao_dispensavel(self, client):
        """Comunicado (ex.: nova dieta) não é atividade — não pode ser marcado
        como realizado/excluído; ele só some sozinho quando a data passa."""
        c, engine = client
        self._seed_lote(engine)
        c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-09",
            "itens": [{"alimento": "Silagem", "quantidade": 400.0, "unidade": "kg"}],
        })
        evento = [e for e in c.get("/agenda/", params={"data": "2026-07-09", "dias": 30}).json()["eventos"]
                  if e.get("tipo") == "nova_dieta"][0]
        assert evento["comunicado"] is True
        chave = evento["id"]

        r = c.post("/agenda/realizados", json={"evento_id": chave})
        assert r.status_code == 400

        depois = [e for e in c.get("/agenda/", params={"data": "2026-07-09", "dias": 30}).json()["eventos"]
                  if e["id"] == chave]
        assert len(depois) == 1

        # Já não vigora mais nem véspera nem dia-de → some sozinho, sem ação do usuário.
        futuro = [e for e in c.get("/agenda/", params={"data": "2026-07-11", "dias": 30}).json()["eventos"]
                  if e["id"] == chave]
        assert len(futuro) == 0


class TestDietaLancamentoApareceNoPlanoPorLote:
    """Bug real reportado pelo dono: uma dieta lançada em "Lançar nova dieta"
    (`DietaLancamento`/`DietaItemProgramado`) nunca aparecia em Plano por
    Lote / Necessidade mensal / baixa automática — essas telas só liam
    `Dieta` (linha congelada do DIETA.csv importado uma vez, nunca escrita
    pela tela de lançamento). `_dietas_e_animais` agora funde as duas fontes,
    por lote, com a dieta lançada tendo prioridade exclusiva sobre o import
    legado do mesmo lote (nunca soma as duas)."""

    def test_dieta_lancada_aparece_no_get_alimentacao(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Animal(numero="2", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.commit()
        c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-01",
            "itens": [{"alimento": "Caroço de algodão", "quantidade": 5.0, "unidade": "kg"}],
        })

        r = c.get("/alimentacao/")
        assert r.status_code == 200
        dados = r.json()
        total = {x["ingrediente"]: x["consumo_dia"] for x in dados["consumo_total"]}
        assert total["Caroço de algodão"] == 5.0  # base "total" (padrão): 5kg é o total do lote/dia, não por cabeça
        lote1 = next(l for l in dados["por_lote"] if l["lote"] == 1)
        assert {i["ingrediente"] for i in lote1["itens"]} == {"Caroço de algodão"}

    def test_dieta_lancada_por_animal_calcula_por_cabeca_certo(self, client):
        """Regressão da mesma classe do bug de `apresentacao_dieta`/
        `contexto_dieta`/`dieta_do_lote_consumo`: aqui na fusão com o legado
        também não pode tratar `quantidade` como total do lote quando a
        dieta foi lançada "por animal"."""
        c, engine = client
        with Session(engine) as s:
            for n in ("1", "2", "3"):
                s.add(Animal(numero=n, categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.commit()
        c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-01", "base_quantidade": "animal",
            "itens": [{"alimento": "Concentrado", "quantidade": 2.0, "unidade": "kg"}],
        })

        total = {x["ingrediente"]: x["consumo_dia"] for x in c.get("/alimentacao/").json()["consumo_total"]}
        assert total["Concentrado"] == 6.0  # 2kg/cabeça * 3 animais — não 2/3 nem 2*3*3

    def test_dieta_lancada_substitui_o_import_legado_do_mesmo_lote_sem_somar(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Animal(numero="2", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            # Import legado do MESMO lote 1 — não pode aparecer mais depois
            # que uma dieta é lançada pra esse lote (senão dobra o consumo).
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Silagem de milho", quantidade=20.0, unidade="kg"))
            s.commit()
        c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": "2026-07-01",
            "itens": [{"alimento": "Caroço de algodão", "quantidade": 5.0, "unidade": "kg"}],
        })

        total = {x["ingrediente"]: x["consumo_dia"] for x in c.get("/alimentacao/").json()["consumo_total"]}
        assert "Silagem de milho" not in total
        assert total["Caroço de algodão"] == 5.0

    def test_lote_sem_dieta_lancada_continua_lendo_o_import_legado(self, client):
        """Zero mudança de comportamento pra quem nunca usou "Lançar nova
        dieta" — lote 2 aqui não tem nenhum DietaLancamento."""
        c, engine = client
        _seed(engine)  # semeia lote 1 com Dieta legada (Silagem de milho)

        total = {x["ingrediente"]: x["consumo_dia"] for x in c.get("/alimentacao/").json()["consumo_total"]}
        assert total["Silagem de milho"] == 40.0


class TestCategoriasAlimento:
    def test_lista_categorias_semeia_padrao(self, client):
        c, engine = client
        r = c.get("/alimentacao/categorias")
        assert r.status_code == 200
        nomes = {cat["nome"] for cat in r.json()}
        assert {"Volumoso", "Concentrado", "Mineral"} <= nomes

    def test_cria_categoria(self, client):
        c, engine = client
        r = c.post("/alimentacao/categorias", json={"nome": "Suplemento"})
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["nome"] == "Suplemento"
        assert corpo["ativo"] is True
        with Session(engine) as s:
            assert s.exec(select(CategoriaAlimento).where(CategoriaAlimento.nome == "Suplemento")).first() is not None

    def test_cria_categoria_duplicada_da_409(self, client):
        c, engine = client
        c.post("/alimentacao/categorias", json={"nome": "Suplemento"})
        r = c.post("/alimentacao/categorias", json={"nome": "Suplemento"})
        assert r.status_code == 409

    def test_atualiza_categoria_renomeia(self, client):
        c, engine = client
        cid = c.post("/alimentacao/categorias", json={"nome": "Antiga"}).json()["id"]
        r = c.put(f"/alimentacao/categorias/{cid}", json={"nome": "Nova", "ativo": False})
        assert r.status_code == 200
        # A rota devolve `cat.model_dump()` logo após o commit sem `refresh` —
        # o objeto fica "expirado" e o corpo da resposta vem vazio; a
        # confirmação real do que foi de fato gravado é via GET/DB.
        with Session(engine) as s:
            cat = s.get(CategoriaAlimento, cid)
            assert cat.nome == "Nova"
            assert cat.ativo is False
        listadas = {c2["nome"]: c2 for c2 in c.get("/alimentacao/categorias").json()}
        assert listadas["Nova"]["ativo"] is False

    def test_atualiza_categoria_para_nome_ja_usado_da_409(self, client):
        c, engine = client
        c.post("/alimentacao/categorias", json={"nome": "A"})
        cid_b = c.post("/alimentacao/categorias", json={"nome": "B"}).json()["id"]
        r = c.put(f"/alimentacao/categorias/{cid_b}", json={"nome": "A"})
        assert r.status_code == 409

    def test_atualiza_categoria_inexistente_da_404(self, client):
        c, engine = client
        r = c.put("/alimentacao/categorias/999", json={"nome": "X"})
        assert r.status_code == 404

    def test_exclui_categoria_sem_uso(self, client):
        c, engine = client
        cid = c.post("/alimentacao/categorias", json={"nome": "Descartavel"}).json()["id"]
        r = c.delete(f"/alimentacao/categorias/{cid}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        with Session(engine) as s:
            assert s.get(CategoriaAlimento, cid) is None

    def test_exclui_categoria_em_uso_da_409(self, client):
        c, engine = client
        cid = c.post("/alimentacao/categorias", json={"nome": "Volumoso teste"}).json()["id"]
        c.post("/alimentacao/alimentos", json={"nome": "Feno teste", "categoria_alimento_id": cid})
        r = c.delete(f"/alimentacao/categorias/{cid}")
        assert r.status_code == 409
        assert "Feno teste" in r.json()["detail"]
        with Session(engine) as s:
            assert s.get(CategoriaAlimento, cid) is not None

    def test_exclui_categoria_inexistente_da_404(self, client):
        c, engine = client
        r = c.delete("/alimentacao/categorias/999")
        assert r.status_code == 404

    def test_semeadura_nao_ressuscita_categoria_apagada(self, client):
        c, engine = client
        r1 = c.get("/alimentacao/categorias")
        volumoso_id = next(cat["id"] for cat in r1.json() if cat["nome"] == "Volumoso")
        r_del = c.delete(f"/alimentacao/categorias/{volumoso_id}")
        assert r_del.status_code == 200
        # (bug pré-existente corrigido) Antes desta sessão esse segundo GET
        # ressuscitava "Volumoso": a semeadura rodava a cada chamada e só
        # olhava se o NOME padrão já existia. Agora só semeia quando a
        # fazenda está com ZERO categorias, então apagar uma padrão de
        # propósito é definitivo — o comportamento antigo era o bug.
        r2 = c.get("/alimentacao/categorias")
        nomes = {cat["nome"] for cat in r2.json()}
        assert "Volumoso" not in nomes
        assert {"Concentrado", "Mineral"} <= nomes


class TestSubcategoriasAlimento:
    """Frente A — hierarquia em dois níveis (raiz -> subcategoria)."""

    def test_cria_subcategoria(self, client):
        c, engine = client
        pai_id = c.post("/alimentacao/categorias", json={"nome": "Concentrado"}).json()["id"]
        r = c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": pai_id})
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["nome"] == "Proteico"
        assert corpo["categoria_pai_id"] == pai_id

    def test_recusa_terceiro_nivel(self, client):
        c, engine = client
        pai_id = c.post("/alimentacao/categorias", json={"nome": "Concentrado"}).json()["id"]
        filha_id = c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": pai_id}).json()["id"]
        r = c.post("/alimentacao/categorias", json={"nome": "Neta", "categoria_pai_id": filha_id})
        assert r.status_code == 409

    def test_recusa_terceiro_nivel_via_put(self, client):
        # Mesma recusa, mas tentando o 3º nível editando uma categoria já
        # existente para apontar a uma subcategoria (não só na criação).
        c, engine = client
        pai_id = c.post("/alimentacao/categorias", json={"nome": "Concentrado"}).json()["id"]
        filha_id = c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": pai_id}).json()["id"]
        neta_id = c.post("/alimentacao/categorias", json={"nome": "Neta"}).json()["id"]
        r = c.put(f"/alimentacao/categorias/{neta_id}", json={"nome": "Neta", "categoria_pai_id": filha_id})
        assert r.status_code == 409

    def test_recusa_ser_pai_de_si_mesma(self, client):
        c, engine = client
        cid = c.post("/alimentacao/categorias", json={"nome": "Concentrado"}).json()["id"]
        r = c.put(f"/alimentacao/categorias/{cid}", json={"nome": "Concentrado", "categoria_pai_id": cid})
        assert r.status_code == 409

    def test_mesmo_nome_sob_pais_diferentes_e_aceito(self, client):
        c, engine = client
        concentrado_id = c.post("/alimentacao/categorias", json={"nome": "Concentrado"}).json()["id"]
        volumoso_id = c.post("/alimentacao/categorias", json={"nome": "Volumoso"}).json()["id"]
        r1 = c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": concentrado_id})
        r2 = c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": volumoso_id})
        assert r1.status_code == 201
        assert r2.status_code == 201

    def test_mesmo_nome_sob_mesmo_pai_e_recusado(self, client):
        c, engine = client
        pai_id = c.post("/alimentacao/categorias", json={"nome": "Concentrado"}).json()["id"]
        c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": pai_id})
        r = c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": pai_id})
        assert r.status_code == 409

    def test_exclui_categoria_com_filha_e_recusado(self, client):
        c, engine = client
        pai_id = c.post("/alimentacao/categorias", json={"nome": "Concentrado"}).json()["id"]
        c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": pai_id})
        r = c.delete(f"/alimentacao/categorias/{pai_id}")
        assert r.status_code == 409
        assert "Proteico" in r.json()["detail"]
        with Session(engine) as s:
            assert s.get(CategoriaAlimento, pai_id) is not None

    def test_lista_categorias_agrupa_filha_logo_apos_o_pai(self, client):
        c, engine = client
        # Zera as categorias padrão semeadas pra não interferir na ordem esperada —
        # filhas primeiro (a API recusa apagar uma categoria com subcategoria,
        # e agora "Concentrado" já nasce com duas semeadas por padrão).
        categorias_iniciais = c.get("/alimentacao/categorias").json()
        for cat in categorias_iniciais:
            if cat["categoria_pai_id"] is not None:
                c.delete(f"/alimentacao/categorias/{cat['id']}")
        for cat in categorias_iniciais:
            if cat["categoria_pai_id"] is None:
                c.delete(f"/alimentacao/categorias/{cat['id']}")
        volumoso_id = c.post("/alimentacao/categorias", json={"nome": "Volumoso"}).json()["id"]
        concentrado_id = c.post("/alimentacao/categorias", json={"nome": "Concentrado"}).json()["id"]
        c.post("/alimentacao/categorias", json={"nome": "Energético", "categoria_pai_id": concentrado_id})
        c.post("/alimentacao/categorias", json={"nome": "Proteico", "categoria_pai_id": concentrado_id})
        c.post("/alimentacao/categorias", json={"nome": "Silagens", "categoria_pai_id": volumoso_id})
        nomes = [cat["nome"] for cat in c.get("/alimentacao/categorias").json()]
        # "Concentrado" vem antes de "Volumoso" (ordem alfabética das raízes),
        # e cada filha aparece logo abaixo do próprio pai, também alfabética
        # entre si — não misturada com as filhas de outra raiz.
        assert nomes == ["Concentrado", "Energético", "Proteico", "Volumoso", "Silagens"]


class TestCategoriaAlimentoIsolamentoFazenda:
    """(A7/A8, bugs pré-existentes corrigidos) `atualizar_categoria_alimento`
    e `excluir_categoria_alimento` não conferiam a fazenda do registro
    encontrado — uma fazenda conseguia editar/apagar categoria de outra só
    sabendo o id. Precisa de duas fazendas de verdade (a suíte principal
    roda com fazenda_id=None / sem isolamento), por isso tem fixture própria
    — mesmo padrão de test_agenda_inducao_fazenda_id.py."""

    @pytest.fixture
    def client_multi_fazenda(self):
        from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            # O router de Alimentação exige contrato ativo + módulo
            # "alimentacao" contratado (`exigir_modulo_contratado`, main.py)
            # — sem isso toda chamada cai em 403 antes mesmo de chegar na
            # checagem de fazenda_id que este teste quer exercer.
            for fid in (1, 2):
                s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="alimentacao", ativo=True))
            s.commit()

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

        class _FakeUser:
            id = 1
            papel = "admin"
            ativo = True
            username = "teste"

        main.app.dependency_overrides[database.get_session] = _get_session_override
        main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

        def _client(fazenda_id: int) -> TestClient:
            main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
            main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fazenda_id
            return TestClient(main.app)

        yield engine, _client

        main.app.dependency_overrides.clear()

    def test_atualiza_categoria_de_outra_fazenda_da_404(self, client_multi_fazenda):
        engine, _client = client_multi_fazenda
        cid = _client(2).post("/alimentacao/categorias", json={"nome": "Só da Fazenda 2"}).json()["id"]
        r = _client(1).put(f"/alimentacao/categorias/{cid}", json={"nome": "Roubada"})
        assert r.status_code == 404
        with Session(engine) as s:
            assert s.get(CategoriaAlimento, cid).nome == "Só da Fazenda 2"

    def test_exclui_categoria_de_outra_fazenda_da_404(self, client_multi_fazenda):
        engine, _client = client_multi_fazenda
        cid = _client(2).post("/alimentacao/categorias", json={"nome": "Também da Fazenda 2"}).json()["id"]
        r = _client(1).delete(f"/alimentacao/categorias/{cid}")
        assert r.status_code == 404
        with Session(engine) as s:
            assert s.get(CategoriaAlimento, cid) is not None


class TestAlimentos:
    def test_lista_alimentos_reflete_cadastro(self, client):
        # O seed de alimentos padrão (`seed_alimentos`) só roda no startup da
        # aplicação, contra o engine real — não neste banco de teste isolado —
        # então a lista começa vazia até algo ser cadastrado pela própria rota.
        c, engine = client
        assert c.get("/alimentacao/alimentos").json() == []
        c.post("/alimentacao/alimentos", json={"nome": "Silagem de teste"})
        nomes = {a["nome"] for a in c.get("/alimentacao/alimentos").json()}
        assert "Silagem de teste" in nomes

    def test_semeadura_nao_ressuscita_alimento_apagado(self, client):
        """Bug real relatado pelo usuário (01/09/2026): "excluí esses
        alimentos várias vezes e eles sempre voltam". `seed_alimentos` rodava
        a cada boot e checava nome a nome — apagar "Corte 21" de propósito só
        durava até o próximo restart do servidor. Agora só semeia quando a
        fazenda está com ZERO alimentos."""
        from fazenda.api.routers.alimentacao import seed_alimentos

        c, engine = client
        with Session(engine) as s:
            seed_alimentos(s, fazenda_id=None)
        nomes_pos_seed = {a["nome"] for a in c.get("/alimentacao/alimentos").json()}
        assert "Corte 21" in nomes_pos_seed

        corte_21_id = next(a["id"] for a in c.get("/alimentacao/alimentos").json() if a["nome"] == "Corte 21")
        r_del = c.delete(f"/alimentacao/alimentos/{corte_21_id}")
        assert r_del.status_code == 200

        # Simula um restart do servidor: chama o seed de novo, no mesmo banco.
        with Session(engine) as s:
            seed_alimentos(s, fazenda_id=None)
        nomes_pos_restart = {a["nome"] for a in c.get("/alimentacao/alimentos").json()}
        assert "Corte 21" not in nomes_pos_restart
        # O restante da lista padrão continua intacto — só o apagado some.
        assert "Milk Proteico" in nomes_pos_restart

    def test_semeadura_nao_duplica_por_diferenca_de_caixa(self, client):
        """Bug real encontrado durante a investigação: a lista de seed usa
        "Ração Pré-parto" (p minúsculo); um alimento já cadastrado como
        "Ração Pré-Parto" (P maiúsculo) não bloqueava mais a nova checagem
        "zero alimentos" (porque já existe pelo menos um), então o seed nunca
        roda de novo e não duplica."""
        from fazenda.api.routers.alimentacao import seed_alimentos

        c, engine = client
        c.post("/alimentacao/alimentos", json={"nome": "Ração Pré-Parto"})
        with Session(engine) as s:
            seed_alimentos(s, fazenda_id=None)
        nomes = [a["nome"] for a in c.get("/alimentacao/alimentos").json()]
        assert nomes.count("Ração Pré-Parto") == 1
        assert "Ração Pré-parto" not in nomes

    def test_cria_alimento_simples(self, client):
        c, engine = client
        r = c.post("/alimentacao/alimentos", json={"nome": "Farelo de soja"})
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["nome"] == "Farelo de soja"
        assert corpo["estoque_vinculado"] == []
        with Session(engine) as s:
            assert s.exec(select(Alimento).where(Alimento.nome == "Farelo de soja")).first() is not None

    def test_cria_alimento_duplicado_da_409(self, client):
        c, engine = client
        c.post("/alimentacao/alimentos", json={"nome": "Farelo de soja"})
        r = c.post("/alimentacao/alimentos", json={"nome": "Farelo de soja"})
        assert r.status_code == 409

    def test_cria_alimento_vincula_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            e = Estoque(nome="Farelo X", categoria="alimento", quantidade=100.0, unidade="kg")
            s.add(e)
            s.commit()
            s.refresh(e)
            estoque_id = e.id

        r = c.post("/alimentacao/alimentos", json={"nome": "Farelo X", "estoque_ids": [estoque_id]})
        assert r.status_code == 201
        vinculados = r.json()["estoque_vinculado"]
        assert len(vinculados) == 1 and vinculados[0]["id"] == estoque_id
        with Session(engine) as s:
            item = s.get(Estoque, estoque_id)
            assert item.alimento_id == r.json()["id"]

    def test_atualiza_alimento_revincula_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            e_a = Estoque(nome="Estoque A", categoria="alimento", quantidade=10.0, unidade="kg")
            e_b = Estoque(nome="Estoque B", categoria="alimento", quantidade=20.0, unidade="kg")
            s.add(e_a)
            s.add(e_b)
            s.commit()
            s.refresh(e_a)
            s.refresh(e_b)
            id_a, id_b = e_a.id, e_b.id

        alimento_id = c.post("/alimentacao/alimentos", json={"nome": "Concentrado X", "estoque_ids": [id_a]}).json()["id"]
        r = c.put(f"/alimentacao/alimentos/{alimento_id}", json={"nome": "Concentrado X", "estoque_ids": [id_b]})
        assert r.status_code == 200
        vinculados = {v["id"] for v in r.json()["estoque_vinculado"]}
        assert vinculados == {id_b}
        with Session(engine) as s:
            assert s.get(Estoque, id_a).alimento_id is None
            assert s.get(Estoque, id_b).alimento_id == alimento_id

    def test_atualiza_alimento_para_nome_ja_usado_da_409(self, client):
        c, engine = client
        c.post("/alimentacao/alimentos", json={"nome": "Alimento A"})
        id_b = c.post("/alimentacao/alimentos", json={"nome": "Alimento B"}).json()["id"]
        r = c.put(f"/alimentacao/alimentos/{id_b}", json={"nome": "Alimento A"})
        assert r.status_code == 409

    def test_atualiza_alimento_inexistente_da_404(self, client):
        c, engine = client
        r = c.put("/alimentacao/alimentos/999", json={"nome": "X"})
        assert r.status_code == 404

    def test_exclui_alimento_desvincula_estoque(self, client):
        c, engine = client
        with Session(engine) as s:
            e = Estoque(nome="Estoque C", categoria="alimento", quantidade=5.0, unidade="kg")
            s.add(e)
            s.commit()
            s.refresh(e)
            estoque_id = e.id

        alimento_id = c.post("/alimentacao/alimentos", json={"nome": "Concentrado Y", "estoque_ids": [estoque_id]}).json()["id"]
        r = c.delete(f"/alimentacao/alimentos/{alimento_id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        with Session(engine) as s:
            assert s.get(Alimento, alimento_id) is None
            assert s.get(Estoque, estoque_id).alimento_id is None

    def test_exclui_alimento_inexistente_da_404(self, client):
        c, engine = client
        r = c.delete("/alimentacao/alimentos/999")
        assert r.status_code == 404


class TestExcluirAlimentoReferenciadoEmOutrasTabelas:
    """Bug real relatado pelo usuário (01/09/2026): "Failed to fetch" ao
    tentar excluir os dois últimos alimentos sem produto de estoque
    vinculado. `Alimento.id` é referenciado por FK opcional em outras 6
    tabelas além de `Estoque` (dieta programada/consumida, análise
    bromatológica, tabela nutricional, biblioteca nutricional da Formulação
    de Dietas e item de simulação) — o `client` padrão usa SQLite sem
    `PRAGMA foreign_keys`, que não reproduz a violação de integridade que o
    Postgres de produção aplica (mesmo achado do animal 1291 em
    exclusoes.py, no mesmo dia). Esta classe usa um engine à parte com FK
    de verdade ligada."""

    @pytest.fixture
    def client_fk(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(engine, "connect")
        def _habilitar_fk(conexao_dbapi, _conn_record):
            conexao_dbapi.execute("PRAGMA foreign_keys=ON")

        SQLModel.metadata.create_all(engine)

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        from fazenda.auth import get_current_user, get_fazenda_atual_id

        class _FakeUser:
            id = 1
            papel = "admin"
            ativo = True
            username = "teste"

        main.app.dependency_overrides[database.get_session] = _get_session_override
        main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        # O teste cria uma Fazenda (id=1) só para as FKs fecharem — mas
        # `exigir_fazenda_selecionada` (main.py) recusa toda rota de fazenda
        # quando existe fazenda cadastrada e a sessão não diz em qual delas
        # está. Selecionar a fazenda aqui é o que o app faz de verdade; o
        # assunto deste teste é a cascata de exclusão, não o isolamento.
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        with TestClient(main.app) as c:
            yield c, engine
        main.app.dependency_overrides.clear()

    def test_exclui_com_referencia_em_todas_as_tabelas(self, client_fk):
        c, engine = client_fk
        with Session(engine) as s:
            # Fazenda + contrato: com a fazenda selecionada (ver fixture), as
            # travas de contrato/módulo passam a valer — antes elas eram
            # puladas junto com o filtro de tenant, pela mesma tolerância a
            # "sem fazenda" que a auditoria fechou.
            s.add(Fazenda(id=1, nome="Fazenda teste"))
            s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
            for _modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=1, modulo=_modulo, preco=0.0, ativo=True))
            s.commit()  # esta fixture liga PRAGMA foreign_keys=ON: a fazenda
                        # precisa existir antes das linhas que apontam pra ela.
            alimento = Alimento(nome="Teste FK", fazenda_id=1)
            s.add(alimento)
            s.commit()
            s.refresh(alimento)
            aid = alimento.id

            lancamento = DietaLancamento(lote=1, data_abertura=HOJE)
            s.add(lancamento)
            s.commit()
            s.refresh(lancamento)
            s.add(DietaItemProgramado(dieta_lancamento_id=lancamento.id, alimento="Teste FK", alimento_id=aid, quantidade=10, unidade="kg"))
            s.add(ConsumoAlimento(data=HOJE, lote=1, alimento="Teste FK", alimento_id=aid, quantidade=5, unidade="kg"))
            s.add(AnaliseBromatologica(data=HOJE, alimento="Teste FK", alimento_id=aid))
            s.add(TabelaNutricionalProduto(nome="Teste FK", alimento_id=aid))
            s.add(AlimentoNutricional(nome="Teste FK", categoria_nasem="Outros", alimento_id=aid))

            simulacao = DietaSimulacao(fazenda_id=1, nome="Simulação teste")
            s.add(simulacao)
            s.commit()
            s.refresh(simulacao)
            s.add(DietaSimulacaoItem(fazenda_id=1, simulacao_id=simulacao.id, alimento_id=aid, nome="Teste FK"))
            s.commit()

        r = c.delete(f"/alimentacao/alimentos/{aid}")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        with Session(engine) as s:
            assert s.get(Alimento, aid) is None
            assert s.exec(select(DietaItemProgramado)).first().alimento_id is None
            assert s.exec(select(ConsumoAlimento)).first().alimento_id is None
            assert s.exec(select(AnaliseBromatologica)).first().alimento_id is None
            assert s.exec(select(TabelaNutricionalProduto)).first().alimento_id is None
            assert s.exec(select(AlimentoNutricional)).first().alimento_id is None
            assert s.exec(select(DietaSimulacaoItem)).first().alimento_id is None


class TestExcluirEstoqueReferenciadoEmOutrasTabelas:
    """Fase 2 do plano de correção de Alimentação (01/09/2026): novos campos
    `estoque_id` em AlimentoNutricional/TabelaNutricionalProduto/
    DietaSimulacaoItem (importação por produto específico) precisam da MESMA
    proteção contra "Failed to fetch" já aplicada à exclusão de Alimento —
    ver TestExcluirAlimentoReferenciadoEmOutrasTabelas acima. Engine à parte
    com FK de verdade ligada (Postgres de produção aplica, SQLite padrão
    dos testes não)."""

    @pytest.fixture
    def client_fk(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(engine, "connect")
        def _habilitar_fk(conexao_dbapi, _conn_record):
            conexao_dbapi.execute("PRAGMA foreign_keys=ON")

        SQLModel.metadata.create_all(engine)

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        from fazenda.auth import get_current_user, get_fazenda_atual_id

        class _FakeUser:
            id = 1
            papel = "admin"
            ativo = True
            username = "teste"

        main.app.dependency_overrides[database.get_session] = _get_session_override
        main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        # O teste cria uma Fazenda (id=1) só para as FKs fecharem — mas
        # `exigir_fazenda_selecionada` (main.py) recusa toda rota de fazenda
        # quando existe fazenda cadastrada e a sessão não diz em qual delas
        # está. Selecionar a fazenda aqui é o que o app faz de verdade; o
        # assunto deste teste é a cascata de exclusão, não o isolamento.
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        with TestClient(main.app) as c:
            yield c, engine
        main.app.dependency_overrides.clear()

    def test_exclui_com_referencia_em_todas_as_tabelas(self, client_fk):
        c, engine = client_fk
        with Session(engine) as s:
            # Fazenda + contrato: com a fazenda selecionada (ver fixture), as
            # travas de contrato/módulo passam a valer — antes elas eram
            # puladas junto com o filtro de tenant, pela mesma tolerância a
            # "sem fazenda" que a auditoria fechou.
            s.add(Fazenda(id=1, nome="Fazenda teste"))
            s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
            for _modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=1, modulo=_modulo, preco=0.0, ativo=True))
            s.commit()  # esta fixture liga PRAGMA foreign_keys=ON: a fazenda
                        # precisa existir antes das linhas que apontam pra ela.
            item = Estoque(nome="Produto FK", finalidade="Ração/Alimento", fazenda_id=1)
            s.add(item)
            s.commit()
            s.refresh(item)
            eid = item.id

            s.add(AlimentoNutricional(nome="Produto FK", categoria_nasem="Outros", estoque_id=eid))
            s.add(TabelaNutricionalProduto(nome="Produto FK", estoque_id=eid))

            simulacao = DietaSimulacao(fazenda_id=1, nome="Simulação teste")
            s.add(simulacao)
            s.commit()
            s.refresh(simulacao)
            s.add(DietaSimulacaoItem(fazenda_id=1, simulacao_id=simulacao.id, estoque_id=eid, nome="Produto FK"))
            s.commit()

        r = c.delete(f"/estoque/{eid}")
        assert r.status_code == 200, r.text
        assert r.json()["excluido"] is True

        with Session(engine) as s:
            assert s.get(Estoque, eid) is None
            assert s.exec(select(AlimentoNutricional)).first().estoque_id is None
            assert s.exec(select(TabelaNutricionalProduto)).first().estoque_id is None
            assert s.exec(select(DietaSimulacaoItem)).first().estoque_id is None


class TestEstoquePreferido:
    """Fase P1, Gap 3 — PUT /alimentacao/alimentos/{id}/estoque-preferido:
    escolha deliberada de qual item de Estoque vinculado recebe a baixa
    quando o Alimento tem 2+ candidatos (ver `_estoque_por_alimento`)."""

    def _alimento_com_dois_estoques(self, c, engine):
        alimento_id = c.post("/alimentacao/alimentos", json={"nome": "Farelo de soja"}).json()["id"]
        with Session(engine) as s:
            e_a = Estoque(nome="Farelo A", quantidade=100.0, unidade="kg", alimento_id=alimento_id)
            e_b = Estoque(nome="Farelo B", quantidade=100.0, unidade="kg", alimento_id=alimento_id)
            s.add(e_a)
            s.add(e_b)
            s.commit()
            s.refresh(e_a)
            s.refresh(e_b)
            return alimento_id, e_a.id, e_b.id

    def test_define_estoque_preferido(self, client):
        c, engine = client
        alimento_id, id_a, id_b = self._alimento_com_dois_estoques(c, engine)
        r = c.put(f"/alimentacao/alimentos/{alimento_id}/estoque-preferido", json={"estoque_id": id_b})
        assert r.status_code == 200
        assert r.json()["estoque_preferido_id"] == id_b
        with Session(engine) as s:
            assert s.get(Alimento, alimento_id).estoque_preferido_id == id_b

    def test_limpa_preferencia_com_null(self, client):
        c, engine = client
        alimento_id, id_a, id_b = self._alimento_com_dois_estoques(c, engine)
        c.put(f"/alimentacao/alimentos/{alimento_id}/estoque-preferido", json={"estoque_id": id_b})
        r = c.put(f"/alimentacao/alimentos/{alimento_id}/estoque-preferido", json={"estoque_id": None})
        assert r.status_code == 200
        assert r.json()["estoque_preferido_id"] is None

    def test_estoque_que_nao_e_candidato_da_400(self, client):
        c, engine = client
        alimento_id, id_a, id_b = self._alimento_com_dois_estoques(c, engine)
        with Session(engine) as s:
            outro = Estoque(nome="Item avulso", quantidade=1.0, unidade="kg")
            s.add(outro)
            s.commit()
            s.refresh(outro)
            outro_id = outro.id
        r = c.put(f"/alimentacao/alimentos/{alimento_id}/estoque-preferido", json={"estoque_id": outro_id})
        assert r.status_code == 400
        with Session(engine) as s:
            assert s.get(Alimento, alimento_id).estoque_preferido_id is None

    def test_alimento_inexistente_da_404(self, client):
        c, engine = client
        r = c.put("/alimentacao/alimentos/999/estoque-preferido", json={"estoque_id": None})
        assert r.status_code == 404


class TestEstoquePreferidoIsolamentoFazenda:
    @pytest.fixture
    def client_multi_fazenda(self):
        from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            for fid in (1, 2):
                s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="alimentacao", ativo=True))
            s.commit()

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

        class _FakeUser:
            id = 1
            papel = "admin"
            ativo = True
            username = "teste"

        main.app.dependency_overrides[database.get_session] = _get_session_override
        main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

        def _client(fazenda_id: int) -> TestClient:
            main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
            main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fazenda_id
            return TestClient(main.app)

        yield engine, _client

        main.app.dependency_overrides.clear()

    def test_alimento_de_outra_fazenda_da_404(self, client_multi_fazenda):
        engine, _client = client_multi_fazenda
        alimento_id = _client(2).post("/alimentacao/alimentos", json={"nome": "Só da Fazenda 2"}).json()["id"]
        r = _client(1).put(f"/alimentacao/alimentos/{alimento_id}/estoque-preferido", json={"estoque_id": None})
        assert r.status_code == 404


class TestEstoqueCategoriaDireta:
    """Fase P1, Gap 2 — PUT /alimentacao/estoque/{id}/categoria: vincula um
    item de Estoque direto a uma CategoriaAlimento, sem depender do cadastro
    de Alimento."""

    def test_define_categoria_direta(self, client):
        c, engine = client
        cat_id = c.post("/alimentacao/categorias", json={"nome": "Volumoso"}).json()["id"]
        with Session(engine) as s:
            e = Estoque(nome="Silagem avulsa", quantidade=10.0, unidade="kg")
            s.add(e)
            s.commit()
            s.refresh(e)
            estoque_id = e.id
        r = c.put(f"/alimentacao/estoque/{estoque_id}/categoria", json={"categoria_alimento_id": cat_id})
        assert r.status_code == 200
        assert r.json()["categoria_alimento_id"] == cat_id
        with Session(engine) as s:
            assert s.get(Estoque, estoque_id).categoria_alimento_id == cat_id

    def test_limpa_categoria_com_null(self, client):
        c, engine = client
        cat_id = c.post("/alimentacao/categorias", json={"nome": "Volumoso"}).json()["id"]
        with Session(engine) as s:
            e = Estoque(nome="Silagem avulsa", quantidade=10.0, unidade="kg", categoria_alimento_id=cat_id)
            s.add(e)
            s.commit()
            s.refresh(e)
            estoque_id = e.id
        r = c.put(f"/alimentacao/estoque/{estoque_id}/categoria", json={"categoria_alimento_id": None})
        assert r.status_code == 200
        assert r.json()["categoria_alimento_id"] is None

    def test_categoria_inexistente_da_404(self, client):
        c, engine = client
        with Session(engine) as s:
            e = Estoque(nome="Silagem avulsa", quantidade=10.0, unidade="kg")
            s.add(e)
            s.commit()
            s.refresh(e)
            estoque_id = e.id
        r = c.put(f"/alimentacao/estoque/{estoque_id}/categoria", json={"categoria_alimento_id": 999})
        assert r.status_code == 404
        with Session(engine) as s:
            assert s.get(Estoque, estoque_id).categoria_alimento_id is None

    def test_estoque_inexistente_da_404(self, client):
        c, engine = client
        r = c.put("/alimentacao/estoque/999/categoria", json={"categoria_alimento_id": None})
        assert r.status_code == 404


class TestEstoqueCategoriaIsolamentoFazenda:
    @pytest.fixture
    def client_multi_fazenda(self):
        from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            for fid in (1, 2):
                s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="alimentacao", ativo=True))
            s.commit()

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

        class _FakeUser:
            id = 1
            papel = "admin"
            ativo = True
            username = "teste"

        main.app.dependency_overrides[database.get_session] = _get_session_override
        main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

        def _client(fazenda_id: int) -> TestClient:
            main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
            main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fazenda_id
            return TestClient(main.app)

        yield engine, _client

        main.app.dependency_overrides.clear()

    def test_estoque_de_outra_fazenda_da_404(self, client_multi_fazenda):
        engine, _client = client_multi_fazenda
        with Session(engine) as s:
            e = Estoque(nome="Só da Fazenda 2", quantidade=10.0, unidade="kg", fazenda_id=2)
            s.add(e)
            s.commit()
            s.refresh(e)
            estoque_id = e.id
        r = _client(1).put(f"/alimentacao/estoque/{estoque_id}/categoria", json={"categoria_alimento_id": None})
        assert r.status_code == 404

    def test_categoria_de_outra_fazenda_da_404(self, client_multi_fazenda):
        engine, _client = client_multi_fazenda
        cat_id_f2 = _client(2).post("/alimentacao/categorias", json={"nome": "Só da Fazenda 2"}).json()["id"]
        with Session(engine) as s:
            e = Estoque(nome="Item da Fazenda 1", quantidade=10.0, unidade="kg", fazenda_id=1)
            s.add(e)
            s.commit()
            s.refresh(e)
            estoque_id = e.id
        r = _client(1).put(f"/alimentacao/estoque/{estoque_id}/categoria", json={"categoria_alimento_id": cat_id_f2})
        assert r.status_code == 404
        with Session(engine) as s:
            assert s.get(Estoque, estoque_id).categoria_alimento_id is None


class TestTabelaNutricionalProdutoDeEstoque:
    """Fase 2 (01/09/2026): "Nome do novo produto" deixa de ser só texto
    livre — POST /alimentacao/tabela-nutricional/produtos aceita `estoque_id`
    do cadastro fechado de Estoque, derivando o nome de lá; texto livre
    continua funcionando como fallback (flag na tela)."""

    def test_cria_produto_a_partir_de_estoque_e_deriva_nome(self, client):
        c, engine = client
        with Session(engine) as s:
            item = Estoque(nome="Concentrado X", finalidade="Ração/Alimento")
            s.add(item)
            s.commit()
            s.refresh(item)
            estoque_id = item.id

        r = c.post("/alimentacao/tabela-nutricional/produtos", json={"estoque_id": estoque_id})
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert corpo["nome"] == "Concentrado X"
        assert corpo["estoque_id"] == estoque_id

    def test_recusa_vincular_o_mesmo_produto_de_estoque_duas_vezes(self, client):
        c, engine = client
        with Session(engine) as s:
            item = Estoque(nome="Concentrado Y", finalidade="Ração/Alimento")
            s.add(item)
            s.commit()
            s.refresh(item)
            estoque_id = item.id

        assert c.post("/alimentacao/tabela-nutricional/produtos", json={"estoque_id": estoque_id}).status_code == 201
        r2 = c.post("/alimentacao/tabela-nutricional/produtos", json={"estoque_id": estoque_id})
        assert r2.status_code == 409

    def test_estoque_id_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/alimentacao/tabela-nutricional/produtos", json={"estoque_id": 999999})
        assert r.status_code == 404

    def test_ainda_aceita_texto_livre_sem_estoque_id(self, client):
        c, _ = client
        r = c.post("/alimentacao/tabela-nutricional/produtos", json={"nome": "Referência genérica"})
        assert r.status_code == 201
        assert r.json()["estoque_id"] is None

    def test_obter_tabela_retorna_estoque_ids_paralelo_a_produto_ids(self, client):
        c, engine = client
        with Session(engine) as s:
            item = Estoque(nome="Concentrado Z", finalidade="Ração/Alimento")
            s.add(item)
            s.commit()
            s.refresh(item)
            estoque_id = item.id
        c.post("/alimentacao/tabela-nutricional/produtos", json={"estoque_id": estoque_id})

        r = c.get("/alimentacao/tabela-nutricional")
        assert r.status_code == 200
        corpo = r.json()
        idx = corpo["alimentos"].index("Concentrado Z")
        assert corpo["estoque_ids"][idx] == estoque_id


class TestGerarComposicaoDeTabelaNutricional:
    """Fase 2 (01/09/2026), pedido do usuário: usar a composição já digitada
    na Tabela Nutricional (texto livre, unidades mistas) pra preencher a
    Biblioteca de Referência por produto, em vez do template genérico. Ver
    fazenda.rules.tabela_nutricional.compor_alimento_nutricional_de_tabela."""

    def _criar_produto_vinculado(self, engine, *, valores: dict[str, str]) -> tuple[int, int, int]:
        from fazenda.models import TabelaNutricionalValor
        with Session(engine) as s:
            alimento = Alimento(nome="Concentrado Proteico Teste")
            s.add(alimento)
            s.commit()
            s.refresh(alimento)
            item = Estoque(nome="Teck Milk 24%", alimento_id=alimento.id, finalidade="Ração/Alimento")
            s.add(item)
            s.commit()
            s.refresh(item)
            produto = TabelaNutricionalProduto(nome="Teck Milk 24%", estoque_id=item.id)
            s.add(produto)
            s.commit()
            s.refresh(produto)
            for nutriente, valor in valores.items():
                s.add(TabelaNutricionalValor(produto_id=produto.id, nutriente=nutriente, valor=valor))
            s.commit()
            return alimento.id, item.id, produto.id

    def test_gera_composicao_convertendo_unidades_e_guarda_o_resto_em_extras(self, client):
        c, engine = client
        alimento_id, estoque_id, produto_id = self._criar_produto_vinculado(engine, valores={
            "Umidade": "125,00 g (Máx)",
            "Proteína Bruta": "240,00 g (Mín)",
            "Cálcio (Mín)": "5.500,00 mg",
            "Vitamina A (Mín)": "13.300,00 UI",
        })
        r = c.post(f"/alimentacao/tabela-nutricional/produtos/{produto_id}/gerar-composicao")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["criado"] is True
        assert corpo["convertidos"]["ms_pct"] == 87.5
        assert corpo["convertidos"]["pb_pct"] == 27.43
        assert corpo["nao_convertidos"]["Vitamina A (Mín)"] == "13.300,00 UI"

        with Session(engine) as s:
            item = s.get(AlimentoNutricional, corpo["alimento_nutricional_id"])
            assert item.alimento_id == alimento_id
            assert item.estoque_id == estoque_id
            assert item.pb_pct == 27.43
            assert item.ms_pct == 87.5
            assert json.loads(item.extras_json)["Vitamina A (Mín)"] == "13.300,00 UI"

    def test_chamar_de_novo_atualiza_em_vez_de_duplicar(self, client):
        c, engine = client
        _, _, produto_id = self._criar_produto_vinculado(engine, valores={"Proteína Bruta": "200,00 g (Mín)"})
        r1 = c.post(f"/alimentacao/tabela-nutricional/produtos/{produto_id}/gerar-composicao")
        assert r1.json()["criado"] is True
        r2 = c.post(f"/alimentacao/tabela-nutricional/produtos/{produto_id}/gerar-composicao")
        assert r2.json()["criado"] is False
        assert r2.json()["alimento_nutricional_id"] == r1.json()["alimento_nutricional_id"]
        with Session(engine) as s:
            assert len(s.exec(select(AlimentoNutricional)).all()) == 1

    def test_produto_sem_vinculo_com_estoque_ou_alimento_da_400(self, client):
        c, engine = client
        with Session(engine) as s:
            produto = TabelaNutricionalProduto(nome="Solto")
            s.add(produto)
            s.commit()
            s.refresh(produto)
            produto_id = produto.id
        r = c.post(f"/alimentacao/tabela-nutricional/produtos/{produto_id}/gerar-composicao")
        assert r.status_code == 400

    def test_produto_inexistente_da_404(self, client):
        c, _ = client
        r = c.post("/alimentacao/tabela-nutricional/produtos/999999/gerar-composicao")
        assert r.status_code == 404

    def test_sem_nenhum_valor_convertivel_da_400(self, client):
        c, engine = client
        _, _, produto_id = self._criar_produto_vinculado(engine, valores={"Vitamina A (Mín)": "13.300,00 UI"})
        r = c.post(f"/alimentacao/tabela-nutricional/produtos/{produto_id}/gerar-composicao")
        assert r.status_code == 400


class TestMateriaSeca:
    def test_lista_semeia_padrao(self, client):
        c, engine = client
        r = c.get("/alimentacao/materia-seca")
        assert r.status_code == 200
        por_nome = {i["nome"]: i["ms_pct"] for i in r.json()}
        assert por_nome["Silagem"] == 33.24
        assert por_nome["Ração Teck Milk 24%"] == 88.0

    def test_upsert_cria_novo_ingrediente(self, client):
        c, engine = client
        r = c.put("/alimentacao/materia-seca", json={"nome": "Casca de soja", "ms_pct": 90.0})
        assert r.status_code == 200
        assert r.json()["ms_pct"] == 90.0
        with Session(engine) as s:
            item = s.exec(select(IngredienteMS).where(IngredienteMS.nome == "Casca de soja")).first()
            assert item is not None and item.ms_pct == 90.0

    def test_upsert_atualiza_existente_sem_duplicar(self, client):
        c, engine = client
        c.put("/alimentacao/materia-seca", json={"nome": "Silagem", "ms_pct": 35.0})
        r = c.get("/alimentacao/materia-seca").json()
        linhas = [i for i in r if i["nome"] == "Silagem"]
        assert len(linhas) == 1
        assert linhas[0]["ms_pct"] == 35.0

    def test_ms_pct_acima_de_100_da_400(self, client):
        c, engine = client
        r = c.put("/alimentacao/materia-seca", json={"nome": "Silagem", "ms_pct": 150.0})
        assert r.status_code == 400

    def test_nome_vazio_da_400(self, client):
        c, engine = client
        r = c.put("/alimentacao/materia-seca", json={"nome": "   ", "ms_pct": 50.0})
        assert r.status_code == 400


class TestAnaliseBromatologica:
    def test_lista_vazia_inicialmente(self, client):
        c, engine = client
        r = c.get("/alimentacao/analise-bromatologica")
        assert r.status_code == 200
        assert r.json() == {"registros": [], "total": 0}

    def test_cria_analise_bromatologica(self, client):
        c, engine = client
        r = c.post("/alimentacao/analise-bromatologica", json={
            "data": "2026-07-01", "alimento": "Silagem de milho", "ms_pct": 34.5, "pb_pct": 8.2,
        })
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["alimento"] == "Silagem de milho"
        assert corpo["ms_pct"] == 34.5
        with Session(engine) as s:
            registro = s.exec(select(AnaliseBromatologica).where(AnaliseBromatologica.alimento == "Silagem de milho")).first()
            assert registro is not None and registro.usuario_id == 1

        r2 = c.get("/alimentacao/analise-bromatologica")
        assert r2.json()["total"] == 1
        assert r2.json()["registros"][0]["alimento"] == "Silagem de milho"

    def test_alimento_vazio_da_400(self, client):
        c, engine = client
        r = c.post("/alimentacao/analise-bromatologica", json={"data": "2026-07-01", "alimento": "   "})
        assert r.status_code == 400

    def test_lista_ordenada_por_data_desc(self, client):
        c, engine = client
        c.post("/alimentacao/analise-bromatologica", json={"data": "2026-01-01", "alimento": "Silagem"})
        c.post("/alimentacao/analise-bromatologica", json={"data": "2026-06-01", "alimento": "Corte 21"})
        registros = c.get("/alimentacao/analise-bromatologica").json()["registros"]
        assert [r["alimento"] for r in registros] == ["Corte 21", "Silagem"]

    # ── Fase P1, Gap 1: AnaliseBromatologica.alimento_id ────────────────────
    def test_resolve_alimento_id_automaticamente_por_nome_exato(self, client):
        c, engine = client
        alimento_id = c.post("/alimentacao/alimentos", json={"nome": "Silagem de milho"}).json()["id"]
        r = c.post("/alimentacao/analise-bromatologica", json={
            "data": "2026-07-01", "alimento": "Silagem de milho", "ms_pct": 34.5,
        })
        assert r.status_code == 201
        assert r.json()["alimento_id"] == alimento_id
        with Session(engine) as s:
            registro = s.exec(select(AnaliseBromatologica).where(AnaliseBromatologica.alimento == "Silagem de milho")).first()
            assert registro.alimento_id == alimento_id

    def test_alimento_id_fica_nulo_quando_nao_ha_alimento_com_esse_nome(self, client):
        c, engine = client
        r = c.post("/alimentacao/analise-bromatologica", json={
            "data": "2026-07-01", "alimento": "Ingrediente sem cadastro",
        })
        assert r.status_code == 201
        assert r.json()["alimento_id"] is None

    def test_respeita_alimento_id_passado_explicitamente(self, client):
        c, engine = client
        # Nome do laudo não bate com o Alimento — o vínculo explícito vence
        # sobre a resolução automática por nome.
        alimento_id = c.post("/alimentacao/alimentos", json={"nome": "Silagem de milho"}).json()["id"]
        r = c.post("/alimentacao/analise-bromatologica", json={
            "data": "2026-07-01", "alimento": "Nome digitado diferente", "alimento_id": alimento_id,
        })
        assert r.status_code == 201
        assert r.json()["alimento_id"] == alimento_id

    def test_alimento_id_explicito_inexistente_da_404(self, client):
        c, engine = client
        r = c.post("/alimentacao/analise-bromatologica", json={
            "data": "2026-07-01", "alimento": "Silagem", "alimento_id": 999,
        })
        assert r.status_code == 404


class TestAnaliseBromatologicaIsolamentoFazenda:
    """`alimento_id` explícito não pode vazar o vínculo pra Alimento de outra
    fazenda — mesma convenção de IDOR (404, não 403) do resto do módulo."""

    @pytest.fixture
    def client_multi_fazenda(self):
        from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            for fid in (1, 2):
                s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="alimentacao", ativo=True))
            s.commit()

        def _get_session_override():
            with Session(engine) as session:
                yield session

        import main
        from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

        class _FakeUser:
            id = 1
            papel = "admin"
            ativo = True
            username = "teste"

        main.app.dependency_overrides[database.get_session] = _get_session_override
        main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

        def _client(fazenda_id: int) -> TestClient:
            main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
            main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fazenda_id
            return TestClient(main.app)

        yield engine, _client

        main.app.dependency_overrides.clear()

    def test_alimento_id_de_outra_fazenda_da_404(self, client_multi_fazenda):
        engine, _client = client_multi_fazenda
        alimento_id_f2 = _client(2).post("/alimentacao/alimentos", json={"nome": "Só da Fazenda 2"}).json()["id"]
        r = _client(1).post("/alimentacao/analise-bromatologica", json={
            "data": "2026-07-01", "alimento": "Roubado", "alimento_id": alimento_id_f2,
        })
        assert r.status_code == 404

    def test_resolucao_automatica_por_nome_nao_cruza_fazenda(self, client_multi_fazenda):
        engine, _client = client_multi_fazenda
        alimento_id_f2 = _client(2).post("/alimentacao/alimentos", json={"nome": "Silagem de milho"}).json()["id"]
        r = _client(1).post("/alimentacao/analise-bromatologica", json={
            "data": "2026-07-01", "alimento": "Silagem de milho",
        })
        assert r.status_code == 201
        assert r.json()["alimento_id"] is None  # não achou "Silagem de milho" na fazenda 1
        assert r.json()["alimento_id"] != alimento_id_f2


class TestEstadoBaixa:
    def test_antes_do_primeiro_acesso_estado_e_none(self, client):
        c, engine = client
        r = c.get("/alimentacao/estado-baixa")
        assert r.status_code == 200
        assert r.json() == {"ultima_data_deducao": None}

    def test_apos_primeiro_acesso_estado_tem_data_de_hoje(self, client):
        c, engine = client
        _seed(engine)
        c.get("/alimentacao/")  # dispara a baixa automática e estabelece a linha de estado
        r = c.get("/alimentacao/estado-baixa")
        assert r.status_code == 200
        assert r.json()["ultima_data_deducao"] == date.today().isoformat()
