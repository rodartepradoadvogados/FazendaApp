"""
BUG 3 — `registrar_pagamento_diaria` só validava `valor <= 0`: não olhava o
saldo devedor, não olhava o vale já adiantado e não olhava o status. Quem
digitasse o total das diárias esquecendo o adiantamento pagava duas vezes,
sem um aviso sequer.

Correção pelo precedente que já existe no módulo (409 + flag booleana de
confirmação, como `confirmar_periodo_pago` em `salvar_dias_diaria`): pagar a
mais continua possível (pode ser legítimo — adiantamento do mês que vem, por
exemplo), mas nunca em silêncio.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaCorrente, ContaGerencial, DiariaPagamento


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


def _conta_corrente(engine) -> int:
    with Session(engine) as s:
        conta = ContaCorrente(banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6")
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


def _diaria_com_vale(c, engine, valor_vale=200.0):
    """5 diárias de R$ 100 (total 500) e um vale de R$ 200 já adiantado —
    saldo devedor real: R$ 300."""
    pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Diarista Pagamento", "tipos": ["Diarista"]}).json()["id"]
    inicio = date.today() - timedelta(days=4)
    diaria = c.post("/cadastro/diarias", json={
        "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": inicio.isoformat(),
    }).json()
    conta_corrente_id = _conta_corrente(engine)
    if valor_vale:
        c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "diaria", "origem_id": diaria["id"], "valor": valor_vale,
            "forma_pagamento": "dinheiro", "data_pagamento": date.today().isoformat(),
            "conta_corrente_id": conta_corrente_id,
        })
    return diaria, conta_corrente_id


class TestPagamentoDiariaExcedente:
    def test_pagar_o_total_esquecendo_o_vale_pede_confirmacao(self, client):
        c, engine = client
        diaria, conta_corrente_id = _diaria_com_vale(c, engine)

        r = c.post(f"/cadastro/diarias/{diaria['id']}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 500.0,
            "conta_corrente_id": conta_corrente_id,
        })
        assert r.status_code == 409, r.text
        detalhe = r.json()["detail"]
        assert detalhe["saldo_devedor"] == 300.0
        assert detalhe["valor_informado"] == 500.0
        assert detalhe["excedente"] == 200.0
        assert detalhe["valor_vale"] == 200.0

        # Nada foi gravado — nem o pagamento, nem o lançamento no extrato.
        with Session(engine) as s:
            assert s.exec(select(DiariaPagamento)).all() == []
            assert s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Diária")).all() == []
        assert c.get("/cadastro/diarias").json()[0]["saldo_devedor"] == 300.0

    def test_pagamento_excedente_confirmado_e_registrado(self, client):
        c, engine = client
        diaria, conta_corrente_id = _diaria_com_vale(c, engine)

        r = c.post(f"/cadastro/diarias/{diaria['id']}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 500.0,
            "conta_corrente_id": conta_corrente_id, "confirmar_excedente": True,
        })
        assert r.status_code == 200, r.text
        assert r.json()["valor_pago"] == 500.0
        assert r.json()["saldo_devedor"] == -200.0

    def test_pagamento_dentro_do_saldo_passa_direto(self, client):
        c, engine = client
        diaria, conta_corrente_id = _diaria_com_vale(c, engine)

        r = c.post(f"/cadastro/diarias/{diaria['id']}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 300.0,
            "conta_corrente_id": conta_corrente_id,
        })
        assert r.status_code == 200, r.text
        assert r.json()["saldo_devedor"] == 0.0

    def test_segundo_pagamento_sobre_saldo_zerado_pede_confirmacao(self, client):
        """O saldo devedor desconta os pagamentos ANTERIORES — quitada a
        diária, qualquer novo pagamento é excedente."""
        c, engine = client
        diaria, conta_corrente_id = _diaria_com_vale(c, engine)
        assert c.post(f"/cadastro/diarias/{diaria['id']}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 300.0,
            "conta_corrente_id": conta_corrente_id,
        }).status_code == 200

        r = c.post(f"/cadastro/diarias/{diaria['id']}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 100.0,
            "conta_corrente_id": conta_corrente_id,
        })
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["saldo_devedor"] == 0.0
        assert r.json()["detail"]["excedente"] == 100.0

    def test_valor_nao_positivo_continua_400(self, client):
        c, engine = client
        diaria, conta_corrente_id = _diaria_com_vale(c, engine, valor_vale=0)
        r = c.post(f"/cadastro/diarias/{diaria['id']}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 0,
            "conta_corrente_id": conta_corrente_id,
        })
        assert r.status_code == 400
