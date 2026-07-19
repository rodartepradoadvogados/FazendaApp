"""
Férias e 13º salário (RH ampliado — item de auditoria "RH ampliado (férias/
13º/eSocial)"). eSocial (envio ao governo) está FORA de escopo — cobre só o
cálculo interno e o lançamento em Contas a Pagar:
- `calcular_ferias`/`calcular_decimo_terceiro` são funções puras (sem banco);
- os endpoints geram o registro de acompanhamento + a conta a pagar, e
  bloqueiam edição/exclusão quando já pagos (mesmo padrão de Folha de
  Pagamento/Empreitada/Contrato).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, DecimoTerceiro, FeriasFuncionario, Pessoa
from fazenda.rules.folha_rh import calcular_decimo_terceiro, calcular_ferias


# ---------------------------------------------------------------------------
# Funções puras de cálculo
# ---------------------------------------------------------------------------
def test_calcular_ferias_sem_abono():
    resultado = calcular_ferias(3000.0, dias_gozados=30, abono_pecuniario_dias=0, percentual_terco=1 / 3)
    assert resultado["valor_ferias"] == 3000.0
    assert resultado["valor_terco_constitucional"] == 1000.0
    assert resultado["valor_abono"] == 0.0
    assert resultado["valor_total"] == 4000.0


def test_calcular_ferias_com_abono_pecuniario():
    # 20 dias gozados + 10 dias vendidos (abono), salário 3000 → dia = 100.
    resultado = calcular_ferias(3000.0, dias_gozados=20, abono_pecuniario_dias=10, percentual_terco=1 / 3)
    assert resultado["valor_ferias"] == 2000.0  # 100 * 20
    assert resultado["valor_terco_constitucional"] == round(2000.0 / 3, 2)
    assert resultado["valor_abono"] == round(100 * 10 * (1 + 1 / 3), 2)  # 1333.33
    assert resultado["valor_total"] == round(
        2000.0 + round(2000.0 / 3, 2) + round(100 * 10 * (1 + 1 / 3), 2), 2
    )


def test_calcular_ferias_dia_fracionado():
    resultado = calcular_ferias(3100.0, dias_gozados=15, abono_pecuniario_dias=0, percentual_terco=1 / 3)
    valor_dia = 3100.0 / 30
    assert resultado["valor_ferias"] == round(valor_dia * 15, 2)


def test_calcular_decimo_terceiro_integral():
    assert calcular_decimo_terceiro(3600.0, 12) == 3600.0


def test_calcular_decimo_terceiro_proporcional():
    # Admitido em julho: 6 meses trabalhados no ano.
    assert calcular_decimo_terceiro(3600.0, 6) == 1800.0
    assert calcular_decimo_terceiro(3000.0, 5) == round(3000.0 / 12 * 5, 2)


# ---------------------------------------------------------------------------
# Endpoints — fixture no mesmo padrão de test_vale_folha.py
# ---------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    # `parametros.get_param` (percentual_terco_constitucional_ferias) lê direto
    # de `fazenda.database.engine`, não da sessão injetada — precisa apontar
    # para o engine de teste (mesmo padrão de test_exclusoes.py).
    monkeypatch.setattr(database, "engine", engine)

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


def _criar_pessoa(engine, salario_base: float = 3000.0) -> int:
    with Session(engine) as s:
        p = Pessoa(nome="Fulano", tipo="Funcionário", salario_base=salario_base, data_admissao=date(2020, 1, 10))
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _payload_ferias(pessoa_id: int, **overrides) -> dict:
    base = {
        "pessoa_id": pessoa_id,
        "periodo_aquisitivo_inicio": "2025-01-10",
        "periodo_aquisitivo_fim": "2026-01-10",
        "dias_direito": 30,
        "dias_gozados": 30,
        "data_inicio_gozo": "2026-02-01",
        "data_fim_gozo": "2026-03-02",
        "abono_pecuniario_dias": 0,
    }
    base.update(overrides)
    return base


def test_criar_ferias_gera_lancamento_financeiro(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3000.0)

    r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id))
    assert r.status_code == 200, r.text
    dados = r.json()
    # O endpoint usa o parâmetro seedado (percentual_terco_constitucional_ferias,
    # padrão 0.3333) — não exatamente 1/3 (diferente das funções puras acima,
    # que recebem o percentual explicitamente).
    assert dados["valor_ferias"] == 3000.0
    assert dados["valor_terco_constitucional"] == round(3000.0 * 0.3333, 2)
    assert dados["valor_total"] == round(3000.0 + round(3000.0 * 0.3333, 2), 2)
    assert dados["status"] == "pendente"
    assert dados["numero_lancamento_gerado"]

    with Session(engine) as s:
        conta = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados["numero_lancamento_gerado"])
        ).first()
        assert conta is not None
        assert conta.valor_total == dados["valor_total"]
        assert conta.tipo_documento == "Férias"
        assert conta.tipo == "despesa"


def test_ferias_sem_salario_base_bloqueia(client):
    c, engine = client
    with Session(engine) as s:
        p = Pessoa(nome="SemSalario", tipo="Funcionário")
        s.add(p)
        s.commit()
        s.refresh(p)
        pessoa_id = p.id

    r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id))
    assert r.status_code == 400, r.text


def test_ferias_paga_bloqueia_edicao_e_exclusao(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3000.0)

    r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id, status="pago", data_pagamento="2026-02-05"))
    assert r.status_code == 200, r.text
    registro_id = r.json()["id"]

    r_put = c.put(f"/cadastro/ferias/{registro_id}", json=_payload_ferias(pessoa_id, dias_gozados=15))
    assert r_put.status_code == 400, r_put.text

    r_del = c.delete(f"/cadastro/ferias/{registro_id}")
    assert r_del.status_code == 400, r_del.text

    with Session(engine) as s:
        assert s.get(FeriasFuncionario, registro_id) is not None


def test_editar_ferias_pendente_recalcula_valor(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3000.0)

    r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id, dias_gozados=30))
    registro_id = r.json()["id"]

    r_put = c.put(f"/cadastro/ferias/{registro_id}", json=_payload_ferias(pessoa_id, dias_gozados=15))
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["valor_ferias"] == 1500.0


def test_abono_pecuniario_acima_do_limite_bloqueia(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
    # Limite é dias_direito // 3 = 10 para 30 dias de direito.
    r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id, dias_gozados=15, abono_pecuniario_dias=15))
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# 13º salário
# ---------------------------------------------------------------------------
def _payload_decimo(pessoa_id: int, **overrides) -> dict:
    base = {"pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12}
    base.update(overrides)
    return base


def test_criar_decimo_terceiro_gera_lancamento_financeiro(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3600.0)

    r = c.post("/cadastro/decimo-terceiro", json=_payload_decimo(pessoa_id))
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["valor_bruto"] == 3600.0
    assert dados["valor_liquido"] == 3600.0
    assert dados["numero_lancamento_gerado"]

    with Session(engine) as s:
        conta = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados["numero_lancamento_gerado"])
        ).first()
        assert conta is not None
        assert conta.valor_total == 3600.0
        assert conta.tipo_documento == "13º salário"


def test_decimo_terceiro_proporcional_admissao(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3600.0)

    r = c.post("/cadastro/decimo-terceiro", json=_payload_decimo(pessoa_id, meses_trabalhados=6))
    assert r.status_code == 200, r.text
    assert r.json()["valor_bruto"] == 1800.0


def test_decimo_terceiro_pago_bloqueia_edicao_e_exclusao(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3600.0)

    r = c.post("/cadastro/decimo-terceiro", json=_payload_decimo(pessoa_id, status="pago", data_pagamento="2026-12-20"))
    assert r.status_code == 200, r.text
    registro_id = r.json()["id"]

    r_put = c.put(f"/cadastro/decimo-terceiro/{registro_id}", json=_payload_decimo(pessoa_id, meses_trabalhados=6))
    assert r_put.status_code == 400, r_put.text

    r_del = c.delete(f"/cadastro/decimo-terceiro/{registro_id}")
    assert r_del.status_code == 400, r_del.text

    with Session(engine) as s:
        assert s.get(DecimoTerceiro, registro_id) is not None


def test_decimo_terceiro_meses_invalidos_bloqueia(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine, salario_base=3600.0)

    r = c.post("/cadastro/decimo-terceiro", json=_payload_decimo(pessoa_id, meses_trabalhados=13))
    assert r.status_code == 400, r.text

    r2 = c.post("/cadastro/decimo-terceiro", json=_payload_decimo(pessoa_id, meses_trabalhados=0))
    assert r2.status_code == 400, r2.text
