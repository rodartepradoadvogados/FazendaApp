"""
Regressão: aplicações de BST de um protocolo de indução de lactação (ou uma
aplicação avulsa) NÃO têm o condão de alterar a data da "próxima aplicação"
de BST da rotina do rebanho inteiro — só uma aplicação de rotina
(POST /agenda/bst/aplicar, que grava Sanidade.atividade="BST") serve de
âncora para esse cálculo.

Cenário relatado em produção: rotina em 16/08 (rebanho inteiro) seguida de 3
doses de indução de lactação de UM animal específico em 19/08, 25/08 e 27/08
— a "próxima aplicação" calculada errado saía de 25/08 + intervalo, quando
deveria sair de 16/08 + intervalo (a indução não conta).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ParametroFazenda, Sanidade
from fazenda.rules.parametros import DEFINICOES

INTERVALO_BST = 14
HOJE = date(2026, 8, 27)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # `intervalo_bst()`/`get_param` leem direto de `fazenda.database.engine`,
    # não da sessão injetada — precisa apontar pro engine de teste (mesmo
    # padrão de test_ajuste_proxima_bst.py).
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        for item in DEFINICOES:
            valor = INTERVALO_BST if item["chave"] == "intervalo_bst" else item["valor"]
            s.add(ParametroFazenda(
                chave=item["chave"], grupo=item["grupo"], label=item["label"],
                valor=str(valor), tipo=item.get("tipo", "int"), unidade=item.get("unidade"),
            ))
        # Rebanho da rotina (16/08) + o animal em indução de lactação + um
        # terceiro animal usado na aplicação avulsa.
        for numero in ["1", "2", "3", "300", "400"]:
            s.add(Animal(numero=numero, grupo_primario="01 - Alta", del_dias=70, sexo="F", ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _proxima_visita_bst(c) -> str:
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()["proxima_visita_bst"]


class TestAncoraBstIgnoraInducaoEAvulso:
    def test_inducao_de_lactacao_nao_move_a_ancora(self, client):
        c, engine = client
        with Session(engine) as s:
            # Rotina do rebanho inteiro em 16/08 (várias matrizes).
            for numero in ["1", "2", "3"]:
                s.add(Sanidade(
                    numero_matriz=numero, atividade="BST", data_aplicacao=date(2026, 8, 16),
                    produto="Lactotropin",
                ))
            # Protocolo de indução de lactação da matriz 300 — mesmo produto
            # BST, mas SEM atividade="BST" (grava protocolo_inducao_lancamento_id
            # em vez disso, como faz _marcar_protocolo_inducao_realizado).
            for d in [date(2026, 8, 19), date(2026, 8, 25), date(2026, 8, 27)]:
                s.add(Sanidade(
                    numero_matriz="300", data_aplicacao=d, produto="Lactotropin",
                    protocolo_inducao_lancamento_id=1,
                ))
            s.commit()

        esperado = date(2026, 8, 16) + timedelta(days=INTERVALO_BST)
        assert _proxima_visita_bst(c) == esperado.isoformat()

    def test_aplicacao_avulsa_tambem_nao_move_a_ancora(self, client):
        c, engine = client
        with Session(engine) as s:
            for numero in ["1", "2", "3"]:
                s.add(Sanidade(
                    numero_matriz=numero, atividade="BST", data_aplicacao=date(2026, 8, 16),
                    produto="Lactotropin",
                ))
            # Aplicação avulsa (Sanidade > Avulso): produto BST, mas sem
            # atividade="BST" e sem protocolo_inducao_lancamento_id — igual
            # ao que criar_aplicacao_sanidade grava.
            s.add(Sanidade(
                numero_matriz="400", data_aplicacao=date(2026, 8, 26), produto="Boostin",
            ))
            s.commit()

        esperado = date(2026, 8, 16) + timedelta(days=INTERVALO_BST)
        assert _proxima_visita_bst(c) == esperado.isoformat()

    def test_nova_aplicacao_de_rotina_atualiza_a_ancora_normalmente(self, client):
        c, engine = client
        with Session(engine) as s:
            for numero in ["1", "2", "3"]:
                s.add(Sanidade(
                    numero_matriz=numero, atividade="BST", data_aplicacao=date(2026, 8, 16),
                    produto="Lactotropin",
                ))
            for d in [date(2026, 8, 19), date(2026, 8, 25), date(2026, 8, 27)]:
                s.add(Sanidade(
                    numero_matriz="300", data_aplicacao=d, produto="Lactotropin",
                    protocolo_inducao_lancamento_id=1,
                ))
            s.commit()

        # Antes da nova rotina: âncora continua em 16/08.
        assert _proxima_visita_bst(c) == (date(2026, 8, 16) + timedelta(days=INTERVALO_BST)).isoformat()

        with Session(engine) as s:
            # Nova aplicação de ROTINA, mais recente que tudo — essa sim deve
            # virar a nova âncora.
            for numero in ["1", "2", "3"]:
                s.add(Sanidade(
                    numero_matriz=numero, atividade="BST", data_aplicacao=date(2026, 8, 30),
                    produto="Lactotropin",
                ))
            s.commit()

        esperado = date(2026, 8, 30) + timedelta(days=INTERVALO_BST)
        assert _proxima_visita_bst(c) == esperado.isoformat()
