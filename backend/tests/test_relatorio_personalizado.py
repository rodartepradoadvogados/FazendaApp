"""Testes do Relatório personalizado (Indicadores > Relatório personalizado)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, OcorrenciaClinica, Parto, Sanidade, Servico


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


def test_sem_limite_de_parametros(client):
    c, engine = client
    catalogo = c.get("/indicadores/relatorio-personalizado/catalogo").json()
    assert len(catalogo) > 10
    ids = [p["id"] for p in catalogo]
    r = c.post("/indicadores/relatorio-personalizado", json={"parametros": ids})
    assert r.status_code == 200
    assert len(r.json()["colunas"]) == len(ids)


def test_colunas_computadas_e_resumo(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="1", sexo="F", ativo=True, data_nasc=hoje - timedelta(days=400)))
        s.add(Parto(numero_matriz="1", data_parto=hoje - timedelta(days=100), ordem_parto=1, sexo_cria_1="F"))
        s.add(Servico(numero_matriz="1", data_servico=hoje - timedelta(days=60), ordem_tentativa=1, diagnostico="POSITIVO"))
        s.add(OcorrenciaClinica(numero_matriz="1", doenca="Mastite clínica", data_ocorrencia=hoje - timedelta(days=30)))
        s.add(Sanidade(numero_matriz="1", produto="Antibiótico X", data_aplicacao=hoje - timedelta(days=20), curada=True))
        s.commit()
    r = c.post("/indicadores/relatorio-personalizado", json={
        "parametros": ["numero", "idade_dias", "numero_servicos", "numero_prenhezes", "dias_gestacao_atual", "numero_mastites"],
    })
    assert r.status_code == 200
    dados = r.json()
    linha = dados["linhas"][0]
    assert linha["idade_dias"] == 400
    assert linha["numero_servicos"] == 1
    assert linha["numero_prenhezes"] == 1
    assert linha["dias_gestacao_atual"] == 60
    assert linha["numero_mastites"] == 1

    resumo = dados["resumo"]
    assert resumo["quantidade_animais"] == 1
    assert resumo["taxa_cura_pct"] == 100.0
    assert resumo["percentual_nascimento_femea_pct"] == 100.0


def test_percentual_perda_prenhez_denominador_respeita_periodo(client):
    # Bug da auditoria (B8): o numerador de "% de perda de prenhez" já
    # respeitava data_de/data_ate (via data_perda_prenhez), mas o denominador
    # somava TODOS os diagnósticos do histórico, sem filtro nenhum — um
    # diagnóstico antigo, fora do período pedido, inflava o denominador e
    # fazia o percentual sair artificialmente baixo.
    c, engine = client
    hoje = date.today()
    data_de, data_ate = hoje - timedelta(days=30), hoje
    with Session(engine) as s:
        s.add(Animal(numero="1", sexo="F", ativo=True, data_nasc=hoje - timedelta(days=800)))
        s.add(Animal(numero="2", sexo="F", ativo=True, data_nasc=hoje - timedelta(days=800)))
        # Dentro do período: diagnosticada positiva e perdeu a prenhez — conta
        # no numerador (perdas) E no denominador (diagnosticados no período).
        s.add(Servico(
            numero_matriz="1", data_servico=hoje - timedelta(days=15), ordem_tentativa=1,
            diagnostico="POSITIVO", data_diagnostico=hoje - timedelta(days=10),
            data_perda_prenhez=hoje - timedelta(days=5),
        ))
        # Fora do período (diagnosticado há 100 dias, período é só os últimos
        # 30): positiva, sem perda — antes do fix contava no denominador
        # mesmo fora do período; agora não deve contar.
        s.add(Servico(
            numero_matriz="2", data_servico=hoje - timedelta(days=105), ordem_tentativa=1,
            diagnostico="POSITIVO", data_diagnostico=hoje - timedelta(days=100),
        ))
        s.commit()
    r = c.post("/indicadores/relatorio-personalizado", json={
        "parametros": ["numero"], "data_de": data_de.isoformat(), "data_ate": data_ate.isoformat(),
    })
    assert r.status_code == 200
    resumo = r.json()["resumo"]
    assert resumo["quantidade_perda_prenhez"] == 1
    # Denominador só o diagnóstico dentro do período (a matriz "1") — não os 2
    # do histórico inteiro. 1/1 = 100%, não 1/2 = 50%.
    assert resumo["percentual_perda_prenhez_pct"] == 100.0
