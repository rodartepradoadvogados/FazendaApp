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
from fazenda.api.routers.cadastro.rh_folha import CODIGO_CONTA_GUIA_DCTF, CODIGO_CONTA_GUIA_FGTS
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
        assert conta.codigo_conta == CODIGO_CONTA_GUIA_FGTS == "3.03.01.07"
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
        assert conta.codigo_conta == CODIGO_CONTA_GUIA_DCTF == "3.03.01.06"
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


# ---------------------------------------------------------------------------
# Contas a Pagar de verdade: lançar a guia (FGTS ou DCTF) tem que criar uma
# ContaGerencial com o codigo_conta certo do plano de contas (finalidade
# administrativa, categoria folha de pagamento — já vinculado ao produto de
# estoque correspondente no plano de contas de cada fazenda), com
# valor/vencimento batendo com o que foi lançado, e rastreável de volta ao
# registro de origem (GuiaFolhaEncargo) pelo numero_lancamento compartilhado
# — mesmo padrão já usado por Folha/Férias/13º (`numero_lancamento_gerado` no
# registro de origem == `numero_lancamento` na ContaGerencial).
# ---------------------------------------------------------------------------
def test_lancar_guia_fgts_gera_conta_a_pagar_com_codigo_de_conta_correto(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 1234.56,
        "data_vencimento": "2026-08-07",
    })
    assert r.status_code == 200, r.text
    guia = r.json()
    assert guia["tipo"] == "fgts"

    with Session(engine) as s:
        conta = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == guia["numero_lancamento"])
        ).first()
        assert conta is not None
        # Código da conta gerencial de FGTS no plano de contas.
        assert conta.codigo_conta == "3.03.01.07"
        # Valor e vencimento batem com o que foi lançado na guia.
        assert conta.valor_total == 1234.56
        assert conta.data_vencimento == date(2026, 8, 7)
        assert conta.tipo == "despesa"
        # Rastreabilidade de volta ao registro de origem na Folha.
        assert conta.numero_lancamento == guia["numero_lancamento"]


def test_lancar_guia_dctf_gera_conta_a_pagar_com_codigo_de_conta_correto(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "dctf", "competencia": "2026-07", "codigo_receita": "1017",
        "valor_principal": 900.0, "valor_multa": 30.0, "valor_juros": 5.5,
        "data_vencimento": "2026-08-20",
    })
    assert r.status_code == 200, r.text
    guia = r.json()
    assert guia["tipo"] == "dctf"
    assert guia["valor_total"] == 935.5

    with Session(engine) as s:
        conta = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == guia["numero_lancamento"])
        ).first()
        assert conta is not None
        # Código da conta gerencial de DCTF no plano de contas.
        assert conta.codigo_conta == "3.03.01.06"
        # Valor (principal + multa + juros) e vencimento batem com a guia.
        assert conta.valor_total == 935.5
        assert conta.data_vencimento == date(2026, 8, 20)
        assert conta.tipo == "despesa"
        # Rastreabilidade de volta ao registro de origem na Folha.
        assert conta.numero_lancamento == guia["numero_lancamento"]


# ---------------------------------------------------------------------------
# PUT/DELETE — corrigir ou apagar uma guia já lançada, mantendo a
# ContaGerencial vinculada em sincronia (ou removendo-a junto).
# ---------------------------------------------------------------------------
def test_editar_guia_fgts_atualiza_registro_e_conta_vinculada(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 1240.0,
        "data_vencimento": "2026-08-20",
    })
    guia_id = r.json()["id"]
    numero_lancamento = r.json()["numero_lancamento"]

    r_put = c.put(f"/cadastro/folha-pagamento/guias/{guia_id}", json={
        "tipo": "fgts", "competencia": "2026-08", "valor_principal": 1500.0,
        "valor_multa": 10.0, "data_vencimento": "2026-09-20", "linha_digitavel": "novaLinha123",
    })
    assert r_put.status_code == 200, r_put.text
    dados = r_put.json()
    assert dados["competencia"] == "2026-08"
    assert dados["valor_total"] == 1510.0
    assert dados["linha_digitavel"] == "novaLinha123"
    # numero_lancamento não muda ao editar (mesma conta a pagar é atualizada).
    assert dados["numero_lancamento"] == numero_lancamento

    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
        assert conta is not None
        assert conta.valor_total == 1510.0
        assert conta.data_vencimento == date(2026, 9, 20)
        assert conta.data_competencia == date(2026, 8, 1)
        assert conta.numero_boleto == "novaLinha123"
        assert conta.codigo_conta == CODIGO_CONTA_GUIA_FGTS


def test_editar_guia_dctf_muda_tipo_para_fgts_atualiza_codigo_conta(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "dctf", "competencia": "2026-07", "codigo_receita": "1017",
        "valor_principal": 900.0, "data_vencimento": "2026-08-20",
    })
    guia_id = r.json()["id"]

    r_put = c.put(f"/cadastro/folha-pagamento/guias/{guia_id}", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 900.0, "data_vencimento": "2026-08-20",
    })
    assert r_put.status_code == 200, r_put.text
    dados = r_put.json()
    assert dados["tipo"] == "fgts"
    assert dados["codigo_receita"] is None  # não se aplica mais fora do DCTF

    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados["numero_lancamento"])).first()
        assert conta.codigo_conta == CODIGO_CONTA_GUIA_FGTS
        assert conta.tipo_documento == "Guia FGTS"


def test_editar_guia_valor_total_zero_da_erro(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 1240.0,
        "data_vencimento": "2026-08-20",
    })
    guia_id = r.json()["id"]
    r_put = c.put(f"/cadastro/folha-pagamento/guias/{guia_id}", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 0.0, "data_vencimento": "2026-08-20",
    })
    assert r_put.status_code == 400


def test_editar_guia_ja_paga_da_erro(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 1240.0,
        "data_vencimento": "2026-08-20",
    })
    numero_lancamento = r.json()["numero_lancamento"]
    guia_id = r.json()["id"]
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
        conta.valor_pago = 1240.0
        conta.data_pagamento = date(2026, 8, 15)
        s.add(conta)
        s.commit()

    r_put = c.put(f"/cadastro/folha-pagamento/guias/{guia_id}", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 1500.0, "data_vencimento": "2026-08-20",
    })
    assert r_put.status_code == 400
    assert "já paga" in r_put.json()["detail"]


def test_editar_guia_inexistente_da_404(client):
    c, engine = client
    r = c.put("/cadastro/folha-pagamento/guias/99999", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 100.0, "data_vencimento": "2026-08-20",
    })
    assert r.status_code == 404


def test_excluir_guia_remove_registro_e_conta_vinculada(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "fgts", "competencia": "2026-07", "valor_principal": 1240.0,
        "data_vencimento": "2026-08-20",
    })
    guia_id = r.json()["id"]
    numero_lancamento = r.json()["numero_lancamento"]

    r_del = c.delete(f"/cadastro/folha-pagamento/guias/{guia_id}")
    assert r_del.status_code == 200, r_del.text
    assert r_del.json() == {"ok": True}

    with Session(engine) as s:
        from fazenda.models import GuiaFolhaEncargo
        assert s.get(GuiaFolhaEncargo, guia_id) is None
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
        assert conta is None

    r_list = c.get("/cadastro/folha-pagamento/guias")
    assert r_list.json() == []


def test_excluir_guia_ja_paga_da_erro(client):
    c, engine = client
    r = c.post("/cadastro/folha-pagamento/guias", json={
        "tipo": "dctf", "competencia": "2026-07", "valor_principal": 900.0,
        "data_vencimento": "2026-08-20",
    })
    guia_id = r.json()["id"]
    numero_lancamento = r.json()["numero_lancamento"]
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
        conta.valor_pago = 900.0
        conta.data_pagamento = date(2026, 8, 15)
        s.add(conta)
        s.commit()

    r_del = c.delete(f"/cadastro/folha-pagamento/guias/{guia_id}")
    assert r_del.status_code == 400
    assert "já paga" in r_del.json()["detail"]

    with Session(engine) as s:
        from fazenda.models import GuiaFolhaEncargo
        assert s.get(GuiaFolhaEncargo, guia_id) is not None


def test_excluir_guia_inexistente_da_404(client):
    c, engine = client
    r = c.delete("/cadastro/folha-pagamento/guias/99999")
    assert r.status_code == 404
