"""
Férias, 13º salário e Rescisão (RH ampliado — item de auditoria "RH ampliado
(férias/13º/eSocial)" e, na parte 2, "regras específicas de rescisão").
eSocial (envio ao governo) está FORA de escopo — cobre só o cálculo interno
e o lançamento em Contas a Pagar:
- `calcular_ferias`/`calcular_decimo_terceiro`/`calcular_rescisao` são
  funções puras (sem banco);
- os endpoints de férias/13º geram o registro de acompanhamento + a conta a
  pagar, e bloqueiam edição/exclusão quando já pagos (mesmo padrão de Folha
  de Pagamento/Empreitada/Contrato); rescisão só gera a conta a pagar (não
  há tabela de acompanhamento dedicada).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, DecimoTerceiro, FeriasFuncionario, Pessoa
from fazenda.rules.folha_rh import calcular_decimo_terceiro, calcular_ferias, calcular_rescisao


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


# ---------------------------------------------------------------------------
# Rescisão — funções puras de cálculo.
#
# Cenário-base conferido manualmente para as 4 modalidades: salário R$3000,
# admitido em 2026-01-20, desligado em 2026-07-20 (exatos 6 meses/0 anos
# completos de casa, dia 20 do mês da rescisão):
# - saldo de salário = 3000/30*20 = 2000.00 (igual nas 4 modalidades);
# - sem_justa_causa: aviso prévio 30 dias (0 anos completos) = 3000/30*30 =
#   3000.00; projeta o fim do contrato para 2026-08-19, o que dá 7 meses
#   "cheios" (regra dos 15 dias) tanto para férias proporcionais (30/12*7 =
#   17.5 dias -> 1750.00 + 1/3 = 583.33 -> 2333.33) quanto para 13º
#   proporcional (3000/12*7 = 1750.00); FGTS estimado 3000*0.08*7 = 1680.00,
#   multa 40% = 672.00; total 2000+3000+2333.33+1750+672 = 9755.33.
# - pedido_demissao: sem aviso prévio, então sem projeção — 6 meses cheios
#   (0 dias de resto) para férias proporcionais (30/12*6=15 dias -> 1500.00 +
#   1/3=500.00 -> 2000.00) e 13º proporcional (3000/12*6=1500.00); sem multa
#   de FGTS; total 2000+2000+1500 = 5500.00.
# ---------------------------------------------------------------------------
def test_calcular_rescisao_sem_justa_causa():
    resultado = calcular_rescisao(3000.0, date(2026, 1, 20), date(2026, 7, 20), "sem_justa_causa")
    assert resultado["saldo_salario"] == {"dias_trabalhados_mes": 20, "valor": 2000.0}
    assert resultado["aviso_previo"]["devido"] is True
    assert resultado["aviso_previo"]["dias"] == 30
    assert resultado["aviso_previo"]["dias_indenizados"] == 30
    assert resultado["aviso_previo"]["valor"] == 3000.0
    assert resultado["ferias_proporcionais"]["meses"] == 7
    assert resultado["ferias_proporcionais"]["valor_total"] == 2333.33
    assert resultado["decimo_terceiro_proporcional"] == {"meses": 7, "valor": 1750.0}
    assert resultado["fgts"]["percentual_multa"] == 0.40
    assert resultado["fgts"]["deposito_total_estimado"] == 1680.0
    assert resultado["fgts"]["multa"] == 672.0
    assert resultado["valor_total"] == 9755.33


def test_calcular_rescisao_pedido_demissao():
    resultado = calcular_rescisao(3000.0, date(2026, 1, 20), date(2026, 7, 20), "pedido_demissao")
    assert resultado["saldo_salario"]["valor"] == 2000.0
    assert resultado["aviso_previo"]["devido"] is False
    assert resultado["aviso_previo"]["dias"] == 0
    assert resultado["aviso_previo"]["valor"] == 0.0
    assert resultado["ferias_proporcionais"]["meses"] == 6
    assert resultado["ferias_proporcionais"]["valor_total"] == 2000.0
    assert resultado["decimo_terceiro_proporcional"] == {"meses": 6, "valor": 1500.0}
    assert resultado["fgts"]["percentual_multa"] == 0.0
    assert resultado["fgts"]["multa"] == 0.0
    assert resultado["valor_total"] == 5500.0


def test_calcular_rescisao_justa_causa_so_saldo_e_ferias_vencidas():
    # Na justa causa perdem-se aviso prévio, férias/13º proporcionais e a
    # multa do FGTS — só saldo de salário e férias vencidas (30 dias, direito
    # já adquirido) permanecem devidos.
    resultado = calcular_rescisao(
        3000.0, date(2026, 1, 20), date(2026, 7, 20), "justa_causa", dias_ferias_vencidas=30,
    )
    assert resultado["aviso_previo"]["valor"] == 0.0
    assert resultado["ferias_proporcionais"]["valor_total"] == 0.0
    assert resultado["decimo_terceiro_proporcional"]["valor"] == 0.0
    assert resultado["fgts"]["multa"] == 0.0
    ferias_vencidas_esperadas = calcular_ferias(3000.0, 30)["valor_total"]
    assert resultado["ferias_vencidas"]["valor_total"] == ferias_vencidas_esperadas
    assert resultado["valor_total"] == round(2000.0 + ferias_vencidas_esperadas, 2)


def test_calcular_rescisao_acordo_mutuo_aviso_pela_metade_e_multa_20_por_cento():
    resultado = calcular_rescisao(3000.0, date(2026, 1, 20), date(2026, 7, 20), "acordo_mutuo")
    assert resultado["aviso_previo"]["dias"] == 15  # metade de 30 (art. 484-A CLT)
    assert resultado["aviso_previo"]["valor"] == 1500.0
    assert resultado["fgts"]["percentual_multa"] == 0.20
    assert resultado["fgts"]["percentual_saque_permitido"] == 0.80


def test_calcular_rescisao_aviso_previo_trabalhado_so_indeniza_dias_extras():
    # 6 anos completos de casa (2020-01-20 a 2026-07-20) -> 30 + 6*3 = 48
    # dias de aviso; se já foi trabalhado, só os 18 dias além dos 30
    # iniciais são indenizados em dinheiro (o resto já foi pago na folha).
    resultado = calcular_rescisao(
        3000.0, date(2020, 1, 20), date(2026, 7, 20), "sem_justa_causa", aviso_previo_trabalhado=True,
    )
    assert resultado["aviso_previo"]["dias"] == 48
    assert resultado["aviso_previo"]["dias_indenizados"] == 18
    assert resultado["aviso_previo"]["valor"] == round(3000.0 / 30 * 18, 2)


def test_calcular_rescisao_aviso_previo_limitado_a_90_dias():
    # Mais de 20 anos de casa -> 30 + 3*anos ultrapassaria 90, mas é limitado.
    resultado = calcular_rescisao(3000.0, date(2000, 1, 1), date(2026, 7, 20), "sem_justa_causa")
    assert resultado["aviso_previo"]["dias"] == 90


def test_calcular_rescisao_tipo_invalido_levanta_erro():
    with pytest.raises(ValueError):
        calcular_rescisao(3000.0, date(2026, 1, 1), date(2026, 6, 1), "invalido")


# ---------------------------------------------------------------------------
# Rescisão — endpoints. Diferente de férias/13º, não há tabela de
# acompanhamento dedicada: `/cadastro/rescisao/calcular` só simula (não
# grava nada) e `/cadastro/rescisao` gera a conta a pagar (mesmo padrão de
# `tipo_documento` usado para listar em `GET /cadastro/rescisao`).
# ---------------------------------------------------------------------------
def _criar_pessoa_com_admissao(engine, salario_base: float, data_admissao: date) -> int:
    with Session(engine) as s:
        p = Pessoa(nome="Fulano Rescisão", tipo="Funcionário", salario_base=salario_base, data_admissao=data_admissao)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _payload_rescisao(pessoa_id: int, **overrides) -> dict:
    base = {
        "pessoa_id": pessoa_id,
        "tipo_rescisao": "sem_justa_causa",
        "data_desligamento": "2026-07-20",
        "dias_ferias_vencidas": 0,
        "aviso_previo_trabalhado": False,
    }
    base.update(overrides)
    return base


def test_simular_rescisao_nao_gera_lancamento(client):
    c, engine = client
    pessoa_id = _criar_pessoa_com_admissao(engine, 3000.0, date(2026, 1, 20))

    r = c.post("/cadastro/rescisao/calcular", json=_payload_rescisao(pessoa_id))
    assert r.status_code == 200, r.text
    # O endpoint usa o parâmetro seedado (percentual_terco_constitucional_ferias,
    # padrão 0.3333) — não exatamente 1/3 (diferente das funções puras acima,
    # que recebem o percentual explicitamente): 9755.33 - 0.06 (arredondamento
    # do 1/3 sobre as férias proporcionais) = 9755.27.
    assert r.json()["valor_total"] == 9755.27

    with Session(engine) as s:
        assert s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Rescisão")).first() is None


def test_criar_rescisao_gera_lancamento_financeiro(client):
    c, engine = client
    pessoa_id = _criar_pessoa_com_admissao(engine, 3000.0, date(2026, 1, 20))

    r = c.post(
        "/cadastro/rescisao",
        json=_payload_rescisao(pessoa_id, status="pago", data_pagamento="2026-07-25"),
    )
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["valor_total"] == 9755.27
    assert dados["numero_lancamento_gerado"]

    with Session(engine) as s:
        conta = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados["numero_lancamento_gerado"])
        ).first()
        assert conta is not None
        assert conta.tipo_documento == "Rescisão"
        assert conta.valor_total == 9755.27
        assert conta.valor_pago == 9755.27
        assert conta.tipo == "despesa"

    r2 = c.get("/cadastro/rescisao")
    assert r2.status_code == 200, r2.text
    assert len(r2.json()) == 1


def test_rescisao_sem_data_admissao_bloqueia(client):
    c, engine = client
    with Session(engine) as s:
        p = Pessoa(nome="SemAdmissao", tipo="Funcionário", salario_base=3000.0)
        s.add(p)
        s.commit()
        s.refresh(p)
        pessoa_id = p.id

    r = c.post("/cadastro/rescisao/calcular", json=_payload_rescisao(pessoa_id))
    assert r.status_code == 400, r.text


def test_rescisao_data_desligamento_anterior_a_admissao_bloqueia(client):
    c, engine = client
    pessoa_id = _criar_pessoa_com_admissao(engine, 3000.0, date(2026, 1, 20))

    r = c.post(
        "/cadastro/rescisao/calcular", json=_payload_rescisao(pessoa_id, data_desligamento="2025-01-01"),
    )
    assert r.status_code == 400, r.text


def test_rescisao_tipo_invalido_bloqueia(client):
    c, engine = client
    pessoa_id = _criar_pessoa_com_admissao(engine, 3000.0, date(2026, 1, 20))

    r = c.post("/cadastro/rescisao/calcular", json=_payload_rescisao(pessoa_id, tipo_rescisao="invalido"))
    assert r.status_code == 400, r.text
