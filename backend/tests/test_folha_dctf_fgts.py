"""
FGTS/DCTF na folha de pagamento (campos opcionais por lançamento) + geração
das guias consolidadas de FGTS/DCTF (contas a pagar de PROJEÇÃO — nenhuma
fórmula legal real de FGTS/DCTF, nenhuma integração com sistemas do governo):
- `_calcular_encargo_projetado`: valor explícito tem prioridade sobre
  percentual×bruto; sem os dois, fica None e não afeta nada;
- `POST /cadastro/folha-pagamento/gerar-guias`: soma o valor_fgts/valor_dctf
  de TODOS os lançamentos da competência, cria duas ContaGerencial com
  vencimento no dia 20 do mês seguinte (editável), e bloqueia duplicata.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers.cadastro import _calcular_encargo_projetado
from fazenda.models import ContaGerencial, FolhaPagamento, Pessoa


# ---------------------------------------------------------------------------
# Função pura de cálculo (percentual vs. valor explícito)
# ---------------------------------------------------------------------------
def test_calcular_encargo_projetado_sem_nada_retorna_none():
    assert _calcular_encargo_projetado(3000.0, None, None) is None


def test_calcular_encargo_projetado_so_percentual():
    assert _calcular_encargo_projetado(3000.0, 8.0, None) == 240.0


def test_calcular_encargo_projetado_so_valor():
    assert _calcular_encargo_projetado(3000.0, None, 250.0) == 250.0


def test_calcular_encargo_projetado_valor_tem_prioridade_sobre_percentual():
    # Os dois preenchidos → valor explícito vence (não soma, não faz média).
    assert _calcular_encargo_projetado(3000.0, 8.0, 999.0) == 999.0


# ---------------------------------------------------------------------------
# Endpoints — mesmo padrão de fixture de test_vale_folha.py/test_folha_rh.py
# ---------------------------------------------------------------------------
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


def _criar_pessoa(engine, nome: str = "Fulano", salario_base: float = 3000.0) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=salario_base)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def test_lancar_folha_sem_fgts_dctf_continua_funcionando(client):
    """Campos em branco — nada muda em relação ao comportamento anterior."""
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
    })
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["valor_fgts"] is None
    assert dados["valor_dctf"] is None
    assert dados["valor_liquido"] == 3000.0  # FGTS/DCTF não afeta o líquido do funcionário


def test_lancar_folha_com_percentual_fgts_dctf_calcula_valor(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
        "percentual_fgts": 8.0, "percentual_dctf": 5.0,
    })
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["valor_fgts"] == 240.0
    assert dados["valor_dctf"] == 150.0
    assert dados["percentual_fgts"] == 8.0
    assert dados["percentual_dctf"] == 5.0


def test_lancar_folha_com_valor_fgts_explicito_prevalece_sobre_percentual(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
        "percentual_fgts": 8.0, "valor_fgts": 500.0,
    })
    assert r.status_code == 200, r.text
    assert r.json()["valor_fgts"] == 500.0


def test_editar_folha_recalcula_fgts_dctf(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
        "percentual_fgts": 8.0,
    })
    registro_id = r.json()["id"]
    assert r.json()["valor_fgts"] == 240.0

    r_put = c.put(f"/cadastro/folha-pagamento/{registro_id}", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 4000.0,
        "percentual_fgts": 8.0,
    })
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["valor_fgts"] == 320.0


# ---------------------------------------------------------------------------
# Geração das guias consolidadas
# ---------------------------------------------------------------------------
def test_preview_guias_soma_todos_os_funcionarios(client):
    c, engine = client
    p1 = _criar_pessoa(engine, "Fulano")
    p2 = _criar_pessoa(engine, "Beltrano")

    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": p1, "competencia": "2026-07", "valor_bruto": 3000.0, "valor_fgts": 240.0, "valor_dctf": 100.0,
    })
    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": p2, "competencia": "2026-07", "valor_bruto": 2000.0, "valor_fgts": 160.0, "valor_dctf": 80.0,
    })
    # Um lançamento de outra competência não deve entrar na soma.
    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": p1, "competencia": "2026-08", "valor_bruto": 3000.0, "valor_fgts": 999.0,
    })

    r = c.get("/cadastro/folha-pagamento/guias-preview", params={"competencia": "2026-07"})
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["valor_fgts"] == 400.0
    assert dados["valor_dctf"] == 180.0
    assert dados["quantidade_lancamentos"] == 2
    assert dados["data_vencimento_sugerida"] == "2026-08-20"
    assert dados["ja_gerado"] is False


def test_gerar_guias_cria_duas_contas_com_vencimento_dia_20_mes_seguinte(client):
    c, engine = client
    p1 = _criar_pessoa(engine, "Fulano")
    p2 = _criar_pessoa(engine, "Beltrano")
    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": p1, "competencia": "2026-07", "valor_bruto": 3000.0, "valor_fgts": 240.0, "valor_dctf": 100.0,
    })
    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": p2, "competencia": "2026-07", "valor_bruto": 2000.0, "valor_fgts": 160.0, "valor_dctf": 80.0,
    })

    r = c.post("/cadastro/folha-pagamento/gerar-guias", json={"competencia": "2026-07"})
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["data_vencimento"] == "2026-08-20"
    contas = dados["contas"]
    assert len(contas) == 2
    fgts = next(x for x in contas if x["tipo_documento"] == "Guia FGTS")
    dctf = next(x for x in contas if x["tipo_documento"] == "Guia DCTF")
    assert fgts["valor_total"] == 400.0
    assert dctf["valor_total"] == 180.0
    assert fgts["data_vencimento"] == "2026-08-20"
    assert fgts["tipo"] == "despesa"
    assert fgts["origem"] == "auto"
    assert fgts["centro_custo"] == "Pecuária Leiteira"

    with Session(engine) as s:
        todas = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento.in_(["Guia FGTS", "Guia DCTF"]))).all()
        assert len(todas) == 2
        assert {c.numero_lancamento for c in todas} == {fgts["numero_lancamento"], dctf["numero_lancamento"]}


def test_gerar_guias_aceita_valor_e_vencimento_editados_antes_de_confirmar(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)
    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0, "valor_fgts": 240.0,
    })

    r = c.post("/cadastro/folha-pagamento/gerar-guias", json={
        "competencia": "2026-07", "valor_fgts": 999.0, "data_vencimento": "2026-08-25",
    })
    assert r.status_code == 200, r.text
    fgts = next(x for x in r.json()["contas"] if x["tipo_documento"] == "Guia FGTS")
    assert fgts["valor_total"] == 999.0
    assert fgts["data_vencimento"] == "2026-08-25"


def test_gerar_guias_bloqueia_duplicata(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)
    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0, "valor_fgts": 240.0, "valor_dctf": 100.0,
    })

    r1 = c.post("/cadastro/folha-pagamento/gerar-guias", json={"competencia": "2026-07"})
    assert r1.status_code == 200, r1.text

    r2 = c.post("/cadastro/folha-pagamento/gerar-guias", json={"competencia": "2026-07"})
    assert r2.status_code == 400, r2.text
    assert "já foram geradas" in r2.json()["detail"]

    # E o preview passa a refletir isso.
    preview = c.get("/cadastro/folha-pagamento/guias-preview", params={"competencia": "2026-07"})
    assert preview.json()["ja_gerado"] is True

    with Session(engine) as s:
        todas = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento.in_(["Guia FGTS", "Guia DCTF"]))).all()
        assert len(todas) == 2  # não duplicou


def test_gerar_guias_sem_lancamentos_na_competencia_falha(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/gerar-guias", json={"competencia": "2026-07"})
    assert r.status_code == 404, r.text


def test_gerar_guias_sem_nenhum_valor_fgts_dctf_lancado_falha(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)
    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
    })
    r = c.post("/cadastro/folha-pagamento/gerar-guias", json={"competencia": "2026-07"})
    assert r.status_code == 400, r.text


def test_gerar_guias_com_apenas_fgts_lancado_cria_so_uma_conta(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)
    c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0, "valor_fgts": 240.0,
    })
    r = c.post("/cadastro/folha-pagamento/gerar-guias", json={"competencia": "2026-07"})
    assert r.status_code == 200, r.text
    contas = r.json()["contas"]
    assert len(contas) == 1
    assert contas[0]["tipo_documento"] == "Guia FGTS"
