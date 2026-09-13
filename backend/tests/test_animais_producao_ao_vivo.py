"""
GET /animais/ — produção AO VIVO por animal (`producao_kg`/`producao_data`/
`producao_origem`), reaproveitando `rules.producao_leiteira.
ultimo_controle_por_animal`/`com_fallback_animal` — as mesmas duas funções
que já resolvem esse contrato no contexto de dieta (ver o histórico do bug
no docstring do módulo). `producao_origem` diz de onde o número veio:
"controle" (ControleLeiteiro lançado no app) ou "congelado" (campo
`Animal.ult_cl_kg`, escrito só pelo parser aposentado do GERAL.csv). Sem
nenhum dos dois, o campo fica `None` — não inventa produção para quem nunca
foi controlado.
"""
from __future__ import annotations

import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ControleLeiteiro


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
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
        # 100: tem ControleLeiteiro lançado pelo app (AO VIVO) — vence o
        # congelado, que aqui está deliberadamente desatualizado (10.0) para
        # comprovar que não é ele quem responde.
        s.add(Animal(numero="100", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - ALTA",
                     ativo=True, ult_cl_kg=10.0, data_ult_leite=date(2026, 1, 1)))
        s.add(ControleLeiteiro(numero_matriz="100", data_controle=date(2026, 8, 10), producao_kg=29.5))
        # 200: nunca teve ControleLeiteiro lançado — só o campo congelado do
        # CSV do Ideagri (importação aposentada).
        s.add(Animal(numero="200", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - ALTA",
                     ativo=True, ult_cl_kg=21.0, data_ult_leite=date(2026, 2, 5)))
        # 300: sem controle e sem campo congelado nenhum — nunca foi
        # controlada, o campo tem que ficar vazio (não inventar produção).
        s.add(Animal(numero="300", categoria_abrev="Novilha", sexo="F", grupo_primario="04 - PRE",
                     ativo=True))
        s.commit()


class TestProducaoOrigem:
    def test_animal_com_controle_usa_o_ao_vivo_e_marca_origem_controle(self, client):
        c, engine = client
        _seed(engine)
        resultado = {a["numero"]: a for a in c.get("/animais/").json()}
        a100 = resultado["100"]
        assert a100["producao_kg"] == 29.5
        assert a100["producao_data"] == "2026-08-10"
        assert a100["producao_origem"] == "controle"
        # O congelado continua no payload (outras telas ainda podem lê-lo) —
        # só não é mais quem responde por `producao_kg` quando há controle.
        assert a100["ult_cl_kg"] == 10.0

    def test_animal_so_com_congelado_marca_origem_congelado(self, client):
        c, engine = client
        _seed(engine)
        resultado = {a["numero"]: a for a in c.get("/animais/").json()}
        a200 = resultado["200"]
        assert a200["producao_kg"] == 21.0
        assert a200["producao_data"] == "2026-02-05"
        assert a200["producao_origem"] == "congelado"

    def test_animal_sem_nenhum_dos_dois_fica_sem_producao(self, client):
        c, engine = client
        _seed(engine)
        resultado = {a["numero"]: a for a in c.get("/animais/").json()}
        a300 = resultado["300"]
        assert a300["producao_kg"] is None
        assert a300["producao_data"] is None
        assert a300["producao_origem"] is None
