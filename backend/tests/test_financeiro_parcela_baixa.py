"""
Testes da baixa de parcela já no nascimento do lançamento (POST /lancamentos):
- uma parcela pode nascer paga (data_pagamento/valor_pago/conta_bancaria/...)
  enquanto as demais nascem em aberto, como hoje;
- GET /lancamentos e GET /contas-a-pagar refletem essa baixa por parcela;
- numero_boleto informado no nível do lançamento + parcelamento vira o
  boleto da 1ª parcela (não duplica nas demais);
- desconto_acrescimo é calculado quando valor_pago != valor_total da parcela.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial


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


def _hoje():
    return date.today()


def test_primeira_parcela_paga_nasce_com_baixa_demais_em_aberto(client):
    c, engine = client
    hoje = _hoje()
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Ração", "quantidade": 1, "valor_unitario": 900.0, "valor_total": 900.0}],
        "data_emissao": hoje.isoformat(),
        "centro_custo": "Pecuária Leiteira",
        "parcelas": [
            {
                "data_vencimento": (hoje + timedelta(days=3)).isoformat(),
                "valor": 300.0,
                "data_pagamento": hoje.isoformat(),
                "valor_pago": 300.0,
                "conta_bancaria": "Banco do Brasil · Agência 3775-3 · Conta corrente 3.615-3",
                "forma_pagamento": "pix",
                "numero_documento_pagamento": "COMP-1",
            },
            {"data_vencimento": (hoje + timedelta(days=5)).isoformat(), "valor": 300.0},
            {"data_vencimento": (hoje + timedelta(days=8)).isoformat(), "valor": 300.0},
        ],
    })
    assert r.status_code == 201, r.text

    with Session(engine) as s:
        contas = s.exec(
            select(ContaGerencial).order_by(ContaGerencial.parcela_num)
        ).all()
        assert len(contas) == 3

        p1, p2, p3 = contas
        assert p1.parcela_num == 1
        assert p1.valor_pago == 300.0
        assert p1.data_pagamento == hoje
        assert p1.conta_bancaria == "Banco do Brasil · Agência 3775-3 · Conta corrente 3.615-3"
        assert p1.forma_pagamento == "pix"
        assert p1.numero_documento_pagamento == "COMP-1"
        assert p1.desconto_acrescimo == 0.0

        for pendente in (p2, p3):
            assert pendente.valor_pago is None
            assert pendente.data_pagamento is None
            assert pendente.conta_bancaria is None


def test_lancamentos_e_contas_a_pagar_refletem_parcela_paga(client):
    c, engine = client
    hoje = _hoje()
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Adubo", "quantidade": 1, "valor_unitario": 900.0, "valor_total": 900.0}],
        "data_emissao": hoje.isoformat(),
        "centro_custo": "Pecuária Leiteira",
        "parcelas": [
            {
                "data_vencimento": (hoje + timedelta(days=2)).isoformat(),
                "valor": 300.0,
                "data_pagamento": hoje.isoformat(),
                "valor_pago": 300.0,
                "conta_bancaria": "Caixa",
                "forma_pagamento": "pix",
            },
            {"data_vencimento": (hoje + timedelta(days=4)).isoformat(), "valor": 300.0},
            {"data_vencimento": (hoje + timedelta(days=6)).isoformat(), "valor": 300.0},
        ],
    })
    assert r.status_code == 201, r.text
    numero_lancamento = r.json()["numero_lancamento"]

    # GET /lancamentos — a parcela paga vem com valor_pago/data_pagamento
    # preenchidos, as outras duas em aberto.
    rl = c.get("/financeiro/lancamentos")
    assert rl.status_code == 200
    registros = [x for x in rl.json()["lancamentos"] if x["numero_lancamento"] == numero_lancamento]
    assert len(registros) == 3
    por_parcela = {x["parcela_num"]: x for x in registros}
    assert por_parcela[1]["valor_pago"] == 300.0
    assert por_parcela[1]["data_pagamento"] == hoje.isoformat()
    assert por_parcela[2]["valor_pago"] is None
    assert por_parcela[3]["valor_pago"] is None

    # GET /contas-a-pagar (janela default de 10 dias) — só as duas parcelas
    # em aberto aparecem; a parcela já paga não aparece como pendente.
    rp = c.get("/financeiro/contas-a-pagar")
    assert rp.status_code == 200
    pendentes = [x for x in rp.json() if x["numero_lancamento"] == numero_lancamento]
    parcelas_pendentes = {x["parcela_num"] for x in pendentes}
    assert parcelas_pendentes == {2, 3}


def test_boleto_do_lancamento_vai_para_primeira_parcela_ao_parcelar(client):
    c, engine = client
    hoje = _hoje()
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Combustível", "quantidade": 1, "valor_unitario": 600.0, "valor_total": 600.0}],
        "data_emissao": hoje.isoformat(),
        "centro_custo": "Pecuária Leiteira",
        "numero_boleto": "34191.79001 01043.510047 91020.150008 1 91230000060000",
        "parcelas": [
            {"data_vencimento": (hoje + timedelta(days=30)).isoformat(), "valor": 300.0},
            {"data_vencimento": (hoje + timedelta(days=60)).isoformat(), "valor": 300.0},
        ],
    })
    assert r.status_code == 201, r.text

    with Session(engine) as s:
        contas = s.exec(select(ContaGerencial).order_by(ContaGerencial.parcela_num)).all()
        assert contas[0].numero_boleto == "34191.79001 01043.510047 91020.150008 1 91230000060000"
        assert contas[1].numero_boleto is None


def test_boleto_por_parcela_nao_e_sobrescrito_pelo_boleto_do_lancamento(client):
    """Se a 1ª parcela já veio com o SEU PRÓPRIO numero_boleto, o
    numero_boleto do lançamento (campo legado, hoje só usado sem
    parcelamento) não deve sobrescrever esse valor mais específico."""
    c, engine = client
    hoje = _hoje()
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Combustível", "quantidade": 1, "valor_unitario": 600.0, "valor_total": 600.0}],
        "data_emissao": hoje.isoformat(),
        "centro_custo": "Pecuária Leiteira",
        "numero_boleto": "BOLETO-DO-LANCAMENTO",
        "parcelas": [
            {"data_vencimento": (hoje + timedelta(days=30)).isoformat(), "valor": 300.0, "numero_boleto": "BOLETO-PARCELA-1"},
            {"data_vencimento": (hoje + timedelta(days=60)).isoformat(), "valor": 300.0},
        ],
    })
    assert r.status_code == 201, r.text

    with Session(engine) as s:
        contas = s.exec(select(ContaGerencial).order_by(ContaGerencial.parcela_num)).all()
        assert contas[0].numero_boleto == "BOLETO-PARCELA-1"
        assert contas[1].numero_boleto is None


def test_desconto_acrescimo_calculado_quando_valor_pago_diferente_do_total(client):
    c, engine = client
    hoje = _hoje()
    r = c.post("/financeiro/lancamentos", json={
        "tipo": "despesa",
        "itens": [{"produto": "Peças", "quantidade": 1, "valor_unitario": 600.0, "valor_total": 600.0}],
        "data_emissao": hoje.isoformat(),
        "centro_custo": "Pecuária Leiteira",
        "parcelas": [
            {
                "data_vencimento": (hoje + timedelta(days=5)).isoformat(),
                "valor": 300.0,
                "data_pagamento": hoje.isoformat(),
                "valor_pago": 290.0,  # pagou com 10 de desconto
                "conta_bancaria": "Caixa",
                "forma_pagamento": "pix",
            },
            {"data_vencimento": (hoje + timedelta(days=35)).isoformat(), "valor": 300.0},
        ],
    })
    assert r.status_code == 201, r.text

    with Session(engine) as s:
        contas = s.exec(select(ContaGerencial).order_by(ContaGerencial.parcela_num)).all()
        assert contas[0].valor_pago == 290.0
        assert contas[0].desconto_acrescimo == -10.0
        assert contas[1].desconto_acrescimo is None
