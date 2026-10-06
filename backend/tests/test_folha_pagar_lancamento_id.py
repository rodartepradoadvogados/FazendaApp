"""Fechamento da folha: as linhas de contrato/empreita/diária e as parcelas dos
cadastros expõem o id da conta a pagar (habilita o botão Pagar), e pagar pelo
endpoint de Ações > Pagamento dá baixa na parcela. Também: conta vencida e em
aberto continua na Agenda (até 30 dias)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial


class _FakeUser:
    id = 1
    papel = "admin"
    ativo = True
    username = "teste"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _contrato_mensal(c):
    p = c.post("/cadastro/pessoas", json={"nome": "Marcos Pereira", "tipos": ["Prestador de serviços"]})
    assert p.status_code == 200, p.text
    pessoa_id = p.json()["id"]
    inicio = date.today() + timedelta(days=1)
    r = c.post("/cadastro/contratos", json={
        "pessoa_id": pessoa_id, "descricao": "Cerca do pasto 3", "valor_total": 4800.0, "forma_pagamento": "mensal",
        "parcelas": [
            {"data_vencimento": inicio.isoformat(), "valor": 2400.0},
            {"data_vencimento": (inicio + timedelta(days=30)).isoformat(), "valor": 2400.0},
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_parcela_do_contrato_traz_lancamento_id_e_paga_pelo_endpoint(client):
    c, engine = client
    _contrato_mensal(c)
    contratos = c.get("/cadastro/contratos").json()
    parcelas = contratos[0]["parcelas"]
    assert len(parcelas) == 2
    assert all(p["lancamento_id"] for p in parcelas)
    assert all(p["status"] == "pendente" for p in parcelas)

    r = c.put(f"/financeiro/lancamentos/{parcelas[0]['lancamento_id']}/pagar", json={
        "data_pagamento": date.today().isoformat(), "valor_pago": 2400.0,
        "forma_pagamento": "pix", "numero_documento_pagamento": "88412",
    })
    assert r.status_code == 200, r.text

    depois = c.get("/cadastro/contratos").json()[0]["parcelas"]
    assert depois[0]["status"] == "pago" and depois[0]["data_pagamento"] == date.today().isoformat()
    assert depois[1]["status"] == "pendente"

    with Session(engine) as s:
        conta = s.get(ContaGerencial, parcelas[0]["lancamento_id"])
        assert conta.forma_pagamento == "pix" and conta.numero_documento_pagamento == "88412"


def test_folha_unificada_expoe_lancamento_id_do_contrato(client):
    c, _ = client
    _contrato_mensal(c)
    linhas = [l for l in c.get("/cadastro/folha-pagamento-unificada").json() if l["tipo"] == "contrato"]
    assert len(linhas) == 2
    assert all(l["lancamento_id"] and l["numero_lancamento"] for l in linhas)
    assert all(l["status"] == "pendente" for l in linhas)


def test_conta_vencida_em_aberto_continua_na_agenda(client):
    c, engine = client
    with Session(engine) as s:
        s.add(ContaGerencial(
            tipo="despesa", descricao="Folha atrasada", valor_total=1980.0, numero_lancamento="LC-2026-00900",
            data_vencimento=date.today() - timedelta(days=3), origem="auto",
        ))
        s.add(ContaGerencial(
            tipo="despesa", descricao="Muito antiga", valor_total=100.0, numero_lancamento="LC-2026-00901",
            data_vencimento=date.today() - timedelta(days=90), origem="auto",
        ))
        s.commit()
    r = c.get("/agenda/")
    assert r.status_code == 200, r.text
    textos = " ".join(e["descricao"] for e in r.json().get("eventos", []))
    assert "Folha atrasada" in textos
    assert "Muito antiga" not in textos
