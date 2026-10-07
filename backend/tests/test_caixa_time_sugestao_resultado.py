"""Caixa do time — sugestão "X% do resultado do mês = R$ Y" (base: resultado líquido da DRE, competência)."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
import fazenda.models  # noqa: F401


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _Fake:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _Fake()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _plano(c, codigo, nome, linha):
    assert c.post("/financeiro/plano-contas", json={"codigo": codigo, "nome": nome}).status_code == 200
    assert c.put(f"/financeiro/plano-contas/{codigo}/linha-dre", json={"linha_dre": linha}).status_code == 200


def _lanc(c, tipo, dia, valor, codigo):
    r = c.post("/financeiro/lancamentos", json={
        "tipo": tipo, "data_emissao": dia, "itens": [{"produto": "x", "valor_total": valor, "codigo_conta_gerencial": codigo}]})
    assert r.status_code == 201, r.text


def _cenario(c):
    _plano(c, "2.01", "Venda de leite", "RECEITA_VENDAS")
    _plano(c, "3.04", "Operacional", "DESPESAS_OPERACIONAIS")
    _lanc(c, "receita", "2026-07-05", 10000.0, "2.01")
    _lanc(c, "despesa", "2026-07-10", 4000.0, "3.04")


def test_sugere_percentual_do_resultado_liquido_do_mes(client):
    c, _ = client
    _cenario(c)
    d = c.get("/cadastro/caixa-time/sugestao-resultado", params={"mes": "2026-07", "percentual": 10}).json()
    assert d["mes"] == "2026-07" and d["resultado_liquido"] == 6000.0 and d["valor_sugerido"] == 600.0
    assert d["percentual"] == 10 and d["regime"] == "competencia"


def test_percentual_padrao_vem_do_parametro_financeiro(client, monkeypatch):
    c, engine = client
    _cenario(c)
    from fazenda.models import ParametroFazenda
    with Session(engine) as s:
        s.add(ParametroFazenda(chave="caixa_time_pct_resultado", valor="7.5", tipo="float", grupo="financeiro", label="x"))
        s.commit()
    # `parametros._linha` abre a própria sessão no engine global: aponta para o banco deste teste.
    monkeypatch.setattr(database, "engine", engine)
    d = c.get("/cadastro/caixa-time/sugestao-resultado", params={"mes": "2026-07"}).json()
    assert d["percentual"] == 7.5 and d["valor_sugerido"] == 450.0


def test_sem_parametro_o_percentual_padrao_e_zero(client):
    c, _ = client
    _cenario(c)
    d = c.get("/cadastro/caixa-time/sugestao-resultado", params={"mes": "2026-07"}).json()
    assert d["percentual"] == 0 and d["valor_sugerido"] == 0.0 and d["resultado_liquido"] == 6000.0


def test_resultado_negativo_nao_gera_sugestao(client):
    c, _ = client
    _plano(c, "3.04", "Operacional", "DESPESAS_OPERACIONAIS")
    _lanc(c, "despesa", "2026-07-10", 1000.0, "3.04")
    d = c.get("/cadastro/caixa-time/sugestao-resultado", params={"mes": "2026-07", "percentual": 10}).json()
    assert d["resultado_liquido"] == -1000.0 and d["valor_sugerido"] == 0.0


def test_avisa_do_que_nao_esta_classificado_na_dre(client):
    c, _ = client
    _cenario(c)
    assert c.post("/financeiro/plano-contas", json={"codigo": "3.99", "nome": "Sem linha"}).status_code == 200
    _lanc(c, "despesa", "2026-07-12", 500.0, "3.99")
    d = c.get("/cadastro/caixa-time/sugestao-resultado", params={"mes": "2026-07", "percentual": 10}).json()
    assert d["nao_classificado"] == 500.0


def test_mes_padrao_e_o_anterior_e_validacoes(client):
    c, _ = client
    hoje = date.today()
    esperado = f"{hoje.year}-{hoje.month - 1:02d}" if hoje.month > 1 else f"{hoje.year - 1}-12"
    assert c.get("/cadastro/caixa-time/sugestao-resultado").json()["mes"] == esperado
    assert c.get("/cadastro/caixa-time/sugestao-resultado", params={"mes": "2026-13"}).status_code == 400
    assert c.get("/cadastro/caixa-time/sugestao-resultado", params={"mes": "2026-07", "percentual": 150}).status_code == 400
