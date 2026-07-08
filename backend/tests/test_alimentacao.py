"""
Testes da Alimentação: consumo por lote, necessidade mensal (com conversão
para sacos) e a baixa automática de estoque por dias decorridos (opção A),
incluindo a segurança contra baixa duplicada sob acesso concorrente.
"""
from __future__ import annotations

import threading
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import AlimentacaoEstado, Animal, Dieta, Estoque, MovimentoEstoque

HOJE = date(2026, 7, 8)


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


def _seed(engine):
    with Session(engine) as s:
        s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
        s.add(Animal(numero="2", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
        s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Silagem de milho", quantidade=20.0, unidade="kg"))
        s.add(Estoque(nome="Silagem de milho", categoria="alimento", quantidade=1000.0, unidade="kg"))
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
        r_meta = c.put("/cadastro/estoque-itens/1", json={"ensacado": True, "kg_por_saco": 25.0})
        assert r_meta.status_code == 200

        r = c.get("/alimentacao/necessidade-mensal")
        assert r.status_code == 200
        item = next(i for i in r.json()["itens"] if i["ingrediente"] == "Silagem de milho")
        assert item["necessidade_mes"] == 1200.0  # 40kg/dia * 30
        assert item["sacos_mes"] == 48  # 1200 / 25


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
