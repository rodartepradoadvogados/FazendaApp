"""
Segurança do webhook do Asaas (fazenda/api/routers/asaas.py::asaas_webhook):
o pedido explícito era "ninguém consiga enviar sinal de pago pro nosso
backend" — três garantias testadas aqui: (1) token errado/ausente é
rejeitado; (2) o `status` do corpo do webhook é ignorado — só o que a API do
Asaas confirma (mockada aqui) decide; (3) replay de um webhook já processado
não repete a liberação de acesso.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["ASAAS_WEBHOOK_TOKEN"] = "segredo-teste"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import CobrancaAsaas, ContratoFazenda, Fazenda


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(ContratoFazenda(fazenda_id=1, status="aguardando_aprovacao", plano="standard"))
        s.add(CobrancaAsaas(fazenda_id=1, tipo="assinatura_mensal", referencia_asaas="pay_123", asaas_customer_id="cus_1", valor=250.0))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def test_token_errado_e_rejeitado(client, monkeypatch):
    c, engine = client
    r = c.post("/asaas/webhook", json={"payment": {"id": "pay_123"}}, headers={"asaas-access-token": "chave-errada"})
    assert r.status_code == 403
    with Session(engine) as s:
        cob = s.exec(select(CobrancaAsaas).where(CobrancaAsaas.referencia_asaas == "pay_123")).first()
        assert cob.status == "emitida"


def test_status_do_corpo_e_ignorado_sem_reconfirmar_na_api(client, monkeypatch):
    """O webhook diz "CONFIRMED", mas a re-consulta (mockada) diz "PENDING" —
    não pode marcar como paga nem liberar acesso."""
    c, engine = client
    from fazenda.rules import asaas as asaas_rules
    monkeypatch.setattr(asaas_rules, "consultar_cobranca", lambda payment_id: {"id": payment_id, "status": "PENDING"})

    r = c.post(
        "/asaas/webhook",
        json={"event": "PAYMENT_CONFIRMED", "payment": {"id": "pay_123", "status": "CONFIRMED"}},
        headers={"asaas-access-token": "segredo-teste"},
    )
    assert r.status_code == 200
    with Session(engine) as s:
        cob = s.exec(select(CobrancaAsaas).where(CobrancaAsaas.referencia_asaas == "pay_123")).first()
        assert cob.status == "emitida"
        contrato = s.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == 1)).first()
        assert contrato.status == "aguardando_aprovacao"


def test_pagamento_reconfirmado_marca_pago_e_libera_acesso(client, monkeypatch):
    c, engine = client
    from fazenda.rules import asaas as asaas_rules
    monkeypatch.setattr(asaas_rules, "consultar_cobranca", lambda payment_id: {"id": payment_id, "status": "RECEIVED"})

    r = c.post(
        "/asaas/webhook",
        json={"event": "PAYMENT_RECEIVED", "payment": {"id": "pay_123"}},
        headers={"asaas-access-token": "segredo-teste"},
    )
    assert r.status_code == 200
    with Session(engine) as s:
        cob = s.exec(select(CobrancaAsaas).where(CobrancaAsaas.referencia_asaas == "pay_123")).first()
        assert cob.status == "paga"
        assert cob.pago_em is not None
        contrato = s.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == 1)).first()
        assert contrato.status == "ativo"


def test_replay_de_webhook_ja_processado_nao_reconsulta(client, monkeypatch):
    c, engine = client
    from fazenda.rules import asaas as asaas_rules
    chamadas = []
    monkeypatch.setattr(asaas_rules, "consultar_cobranca", lambda payment_id: chamadas.append(payment_id) or {"id": payment_id, "status": "RECEIVED"})

    r1 = c.post("/asaas/webhook", json={"payment": {"id": "pay_123"}}, headers={"asaas-access-token": "segredo-teste"})
    assert r1.status_code == 200
    assert len(chamadas) == 1

    r2 = c.post("/asaas/webhook", json={"payment": {"id": "pay_123"}}, headers={"asaas-access-token": "segredo-teste"})
    assert r2.status_code == 200
    assert r2.json().get("ja_processado") is True
    assert len(chamadas) == 1  # não reconsultou de novo — idempotente
