"""
FGTS/DCTF na folha de pagamento:
- `_calcular_encargo_projetado`: valor explícito tem prioridade sobre
  percentual×bruto; sem os dois, fica None e não afeta nada (campos
  opcionais por lançamento de folha, informativos).
- `POST /cadastro/folha-pagamento/guias`: lança uma guia de FGTS/DCTF de
  verdade (manual ou por leitura automática), criando a conta a pagar E o
  registro estruturado em GuiaFolhaEncargo — substitui o antigo "gerar
  guias" (soma projetada sem vínculo com guia real, removido por decisão
  do usuário).
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
# Lançamento de guia de FGTS/DCTF (manual ou por leitura automática)
# ---------------------------------------------------------------------------
def test_lancar_guia_fgts_cria_conta_a_pagar_e_registro_estruturado(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 1240.0,
        "data_vencimento": "2026-08-20", "linha_digitavel": "858700000012400123456789012345678901234567",
    })
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["tipo"] == "fgts"
    assert dados["valor_total"] == 1240.0
    assert dados["origem"] == "manual"
    numero_lancamento = dados["numero_lancamento"]
    assert numero_lancamento

    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
        assert conta is not None
        assert conta.tipo_documento == "Guia FGTS"
        assert conta.valor_total == 1240.0
        assert conta.data_vencimento == date(2026, 8, 20)
        assert conta.numero_boleto == "858700000012400123456789012345678901234567"


def test_lancar_guia_dctf_soma_principal_multa_juros_no_valor_total(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "dctf", "competencia": "2026-07", "codigo_receita": "1017",
        "valor_principal": 850.0, "valor_multa": 20.0, "valor_juros": 22.5,
        "data_vencimento": "2026-08-20", "origem": "leitura_automatica",
    })
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["tipo"] == "dctf"
    assert dados["codigo_receita"] == "1017"
    assert dados["valor_total"] == 892.5
    assert dados["origem"] == "leitura_automatica"

    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados["numero_lancamento"])).first()
        assert conta.tipo_documento == "Guia DCTF"
        assert conta.valor_total == 892.5


def test_lancar_guia_tipo_invalido_da_erro(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "outro", "competencia": "2026-07", "valor_principal": 100.0, "data_vencimento": "2026-08-20",
    })
    assert r.status_code == 400


def test_lancar_guia_valor_total_zero_da_erro(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 0.0, "data_vencimento": "2026-08-20",
    })
    assert r.status_code == 400


def test_listar_guias_traz_as_mais_recentes_primeiro(client):
    c, engine = client
    c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "fgts", "competencia": "2026-06", "valor_principal": 100.0, "data_vencimento": "2026-07-20",
    })
    c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "dctf", "competencia": "2026-07", "valor_principal": 200.0, "data_vencimento": "2026-08-20",
    })
    r = c.get("/cadastro/folha-pagamento/guias")
    assert r.status_code == 200, r.text
    competencias = [g["competencia"] for g in r.json()]
    assert competencias == ["2026-07", "2026-06"]
