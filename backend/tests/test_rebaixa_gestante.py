"""Rebaixa "gestante" do texto de categoria (GERAL.csv) ao lançar toque/retoque NEGATIVO ou PERDA de prenhez.

Decisão do dono: toque negativo efetivo no serviço vigente ou perda rebaixa "gestante"; positivo, indefinido e
serviço vigente positivo em outro lançamento NÃO rebaixam. Ver `fazenda/rules/rebaixa_gestante.py`.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Servico
from fazenda.rules.lactacao import categoria_sem_gestacao
from fazenda.rules.rebaixa_gestante import prenhez_acabou_sem_parto

HOJE = date.today()


@pytest.fixture
def ctx():
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


def _animal(engine, numero, categoria, abrev=None):
    with Session(engine) as s:
        s.add(Animal(numero=numero, sexo="F", ativo=True, categoria_completa=categoria, categoria_abrev=abrev or categoria))
        s.commit()


def _servico(engine, numero, dias_atras, **kw) -> int:
    with Session(engine) as s:
        sv = Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), **kw)
        s.add(sv)
        s.commit()
        s.refresh(sv)
        return sv.id


def _categoria(engine, numero) -> tuple[str, str]:
    with Session(engine) as s:
        a = s.exec(select(Animal).where(Animal.numero == numero)).first()
        return a.categoria_completa, a.categoria_abrev


def _diag(c, numero, resultado, dias_atras=0):
    return c.post("/reproducao/diagnostico", json={
        "numero_matriz": numero, "data_diagnostico": (HOJE - timedelta(days=dias_atras)).isoformat(),
        "resultado": resultado,
    })


class TestFuncaoPura:
    def test_apos_parto_false_nao_acrescenta_pev(self):
        assert categoria_sem_gestacao("Vaca ges. lac.", apos_parto=False) == "Vaca vaz. lac."
        assert categoria_sem_gestacao("Novilha ges.", apos_parto=False) == "Novilha vaz."
        assert categoria_sem_gestacao("Novilha gestante", apos_parto=False) == "Novilha vazia"
        assert categoria_sem_gestacao("Vaca vaz. apt. lac.", apos_parto=False) == "Vaca vaz. apt. lac."
        # comportamento de parto/aborto preservado
        assert categoria_sem_gestacao("Vaca ges. lac.") == "Vaca vaz. pev lac."

    def test_prenhez_acabou_sem_parto(self):
        pos = Servico(numero_matriz="1", data_servico=HOJE - timedelta(days=90), diagnostico="POSITIVO")
        neg = Servico(numero_matriz="1", data_servico=HOJE - timedelta(days=30), diagnostico="NEGATIVO")
        assert prenhez_acabou_sem_parto([neg], None) is True
        assert prenhez_acabou_sem_parto([pos, neg], None) is False  # outro serviço vigente positivo
        assert prenhez_acabou_sem_parto([pos], None) is False
        assert prenhez_acabou_sem_parto([], None) is False
        # serviço negativo ANTERIOR ao último parto não conta
        assert prenhez_acabou_sem_parto([neg], HOJE - timedelta(days=10)) is False
        perdeu = Servico(numero_matriz="1", data_servico=HOJE - timedelta(days=90), diagnostico="POSITIVO",
                         data_perda_prenhez=HOJE)
        assert prenhez_acabou_sem_parto([perdeu], None) is True


class TestRebaixaPeloEndpoint:
    def test_toque_negativo_rebaixa_novilha_gestante(self, ctx):
        c, engine = ctx
        _animal(engine, "10", "Novilha gestante", "Novilha ges.")
        _servico(engine, "10", 40)
        assert _diag(c, "10", "negativo").status_code == 200
        assert _categoria(engine, "10") == ("Novilha vazia", "Novilha vaz.")
        animal = next(a for a in c.get("/animais/").json() if a["numero"] == "10")
        assert animal["categoria_completa"] == "Novilha vazia"

    def test_reconfirmacao_negativa_rebaixa_vaca(self, ctx):
        c, engine = ctx
        _animal(engine, "11", "Vaca ges. lac.")
        _servico(engine, "11", 70, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=40), retoque=True)
        r = _diag(c, "11", "negativo")  # 2º exame -> reconfirmação NEGATIVA
        assert r.status_code == 200 and r.json()["diagnostico_reconfirmacao"] == "NEGATIVO"
        assert _categoria(engine, "11") == ("Vaca vaz. lac.", "Vaca vaz. lac.")

    def test_endpoint_reconfirmacao_negativa_rebaixa(self, ctx):
        c, engine = ctx
        _animal(engine, "12", "Vaca gestante 2ª lact.")
        _servico(engine, "12", 70, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=40))
        r = c.post("/reproducao/reconfirmacao", json={
            "numero_matriz": "12", "data_reconfirmacao": HOJE.isoformat(), "resultado": "negativo"})
        assert r.status_code == 200
        assert _categoria(engine, "12")[0] == "Vaca vazia 2ª lact."

    def test_perda_prenhez_rebaixa(self, ctx):
        c, engine = ctx
        _animal(engine, "13", "Novilha ges.")
        _servico(engine, "13", 120, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=90))
        r = c.post("/reproducao/perda-prenhez", json={
            "numero_matriz": "13", "data_perda_prenhez": HOJE.isoformat(), "motivo": "aborto"})
        assert r.status_code == 200
        assert _categoria(engine, "13") == ("Novilha vaz.", "Novilha vaz.")

    def test_edicao_do_servico_com_perda_rebaixa(self, ctx):
        c, engine = ctx
        _animal(engine, "14", "Vaca ges. lac.")
        sid = _servico(engine, "14", 120, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=90))
        r = c.put(f"/reproducao/servicos/{sid}", json={"data_perda_prenhez": HOJE.isoformat(), "motivo_perda_prenhez": "aborto"})
        assert r.status_code == 200, r.text
        assert _categoria(engine, "14")[0] == "Vaca vaz. lac."

    def test_toque_positivo_nao_rebaixa(self, ctx):
        c, engine = ctx
        _animal(engine, "15", "Novilha gestante")
        _servico(engine, "15", 40)
        assert _diag(c, "15", "retoque").status_code == 200
        assert _categoria(engine, "15")[0] == "Novilha gestante"

    def test_indefinido_nao_rebaixa(self, ctx):
        c, engine = ctx
        _animal(engine, "16", "Novilha gestante")
        _servico(engine, "16", 40)
        assert _diag(c, "16", "indefinido").status_code == 200
        assert _categoria(engine, "16")[0] == "Novilha gestante"

    def test_outro_servico_vigente_positivo_nao_rebaixa(self, ctx):
        c, engine = ctx
        _animal(engine, "17", "Vaca ges. lac.")
        _servico(engine, "17", 100, diagnostico="POSITIVO", data_diagnostico=HOJE - timedelta(days=70))
        _servico(engine, "17", 20)  # reinseminação em aberto, recebe o toque negativo
        assert _diag(c, "17", "negativo").status_code == 200
        assert _categoria(engine, "17")[0] == "Vaca ges. lac."

    def test_sem_marca_de_gestacao_nao_mexe(self, ctx):
        c, engine = ctx
        _animal(engine, "18", "Vaca vazia 3ª lact.")
        _servico(engine, "18", 40)
        assert _diag(c, "18", "negativo").status_code == 200
        assert _categoria(engine, "18")[0] == "Vaca vazia 3ª lact."
