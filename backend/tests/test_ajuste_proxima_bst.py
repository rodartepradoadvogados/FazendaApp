"""
POST /producao/bst/ajustar-proxima-aplicacao — corrige manualmente a data da
próxima aplicação de BST (rebanho inteiro), com dois modos:
1) "intervalo": recalcula o parâmetro `intervalo_bst` a partir da última
   aplicação real até a nova data.
2) "referencia": mantém o intervalo, mas passa a contar os próximos ciclos a
   partir da nova data (via `bst_ajuste_ancora_data`).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, ParametroFazenda, Sanidade
from fazenda.rules.parametros import DEFINICOES


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # `parametros.get_param`/`get_param_date` (intervalo_bst, bst_ajuste_ancora_data)
    # leem direto de `fazenda.database.engine`, não da sessão injetada — precisa
    # apontar para o engine de teste (mesmo padrão de test_relatorio_custo_hectare.py).
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        for item in DEFINICOES:
            s.add(ParametroFazenda(
                chave=item["chave"], grupo=item["grupo"], label=item["label"],
                valor=str(item["valor"]), tipo=item.get("tipo", "int"), unidade=item.get("unidade"),
            ))
        s.add(Animal(numero="300", grupo_primario="01 - Alta", del_dias=70, sexo="F", ativo=True))
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


def _lancar_bst(engine, numero: str, data_aplicacao: date):
    with Session(engine) as s:
        s.add(Sanidade(numero_matriz=numero, atividade="BST", data_aplicacao=data_aplicacao, produto="Lactotropin"))
        s.commit()


def _param(engine, chave: str) -> str | None:
    with Session(engine) as s:
        row = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == chave)).first()
        return row.valor if row else None


class TestModoIntervalo:
    def test_recalcula_intervalo_a_partir_da_ultima_aplicacao(self, client):
        c, engine = client
        ultima = date.today() - timedelta(days=5)
        _lancar_bst(engine, "300", ultima)

        nova_data = ultima + timedelta(days=20)
        r = c.post("/producao/bst/ajustar-proxima-aplicacao", json={
            "nova_data": nova_data.isoformat(), "modo": "intervalo",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["novo_intervalo"] == 20
        assert _param(engine, "intervalo_bst") == "20"

    def test_sem_aplicacao_real_rejeita(self, client):
        c, engine = client
        r = c.post("/producao/bst/ajustar-proxima-aplicacao", json={
            "nova_data": date.today().isoformat(), "modo": "intervalo",
        })
        assert r.status_code == 400

    def test_reflete_na_agenda(self, client):
        c, engine = client
        ultima = date.today() - timedelta(days=5)
        _lancar_bst(engine, "300", ultima)
        nova_data = ultima + timedelta(days=20)
        c.post("/producao/bst/ajustar-proxima-aplicacao", json={
            "nova_data": nova_data.isoformat(), "modo": "intervalo",
        })
        r = c.get("/agenda/")
        assert r.json()["proxima_visita_bst"] == nova_data.isoformat()
        assert r.json()["intervalo_bst"] == 20


class TestModoReferencia:
    def test_grava_ancora_manual_e_reflete_na_agenda(self, client):
        c, engine = client
        ultima = date.today() - timedelta(days=3)
        _lancar_bst(engine, "300", ultima)

        # Sem ajuste: próxima = última + 12 (padrão)
        r0 = c.get("/agenda/")
        assert r0.json()["proxima_visita_bst"] == (ultima + timedelta(days=12)).isoformat()

        nova_data = date.today() + timedelta(days=9)
        r = c.post("/producao/bst/ajustar-proxima-aplicacao", json={
            "nova_data": nova_data.isoformat(), "modo": "referencia",
        })
        assert r.status_code == 200
        assert r.json()["intervalo_bst"] == 12
        assert _param(engine, "intervalo_bst") == "12"
        assert _param(engine, "bst_ajuste_ancora_data") == (nova_data - timedelta(days=12)).isoformat()

        r2 = c.get("/agenda/")
        assert r2.json()["proxima_visita_bst"] == nova_data.isoformat()

    def test_aplicacao_real_mais_recente_retoma_prioridade(self, client):
        c, engine = client
        ultima = date.today() - timedelta(days=3)
        _lancar_bst(engine, "300", ultima)
        nova_data = date.today() + timedelta(days=9)
        c.post("/producao/bst/ajustar-proxima-aplicacao", json={
            "nova_data": nova_data.isoformat(), "modo": "referencia",
        })

        # Uma nova aplicação real, mais recente que a âncora manual, deve
        # voltar a mandar no cálculo.
        nova_aplicacao_real = date.today()
        _lancar_bst(engine, "300", nova_aplicacao_real)
        r = c.get("/agenda/")
        assert r.json()["proxima_visita_bst"] == (nova_aplicacao_real + timedelta(days=12)).isoformat()


class TestModoInvalido:
    def test_modo_invalido_rejeita(self, client):
        c, engine = client
        r = c.post("/producao/bst/ajustar-proxima-aplicacao", json={
            "nova_data": date.today().isoformat(), "modo": "outro",
        })
        assert r.status_code == 400
