"""
Transferência entre contas correntes (Configurações > Parâmetros financeiros
> Conta corrente > "Transferir entre contas") — POST/GET
/financeiro/contas-correntes/transferencias.

Modelagem: tabela dedicada `TransferenciaContas` (dois FKs para
ContaCorrente, um valor, uma data), em vez de um novo tipo de ContaGerencial
— ver docstring do model em fazenda/models/financeiro.py. Por isso a
transferência nunca deve aparecer em /financeiro/dre nem em
/financeiro/lancamentos (que só leem ContaGerencial/LancamentoItem): ela só
se manifesta no saldo calculado das contas, via
calcular_saldos_contas_correntes.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers.financeiro import rotulo_conta_corrente
from fazenda.models import ContaCorrente, ContaGerencial, TransferenciaContas


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
        c.engine = engine
        yield c

    main.app.dependency_overrides.clear()


def _criar_contas(engine) -> tuple[int, int]:
    with Session(engine) as s:
        origem = ContaCorrente(banco="Banco do Brasil", agencia="1111-1", numero_conta="1.000-0")
        destino = ContaCorrente(banco="Sicredi", agencia="2222-2", numero_conta="2.000-0")
        s.add(origem)
        s.add(destino)
        s.commit()
        s.refresh(origem)
        s.refresh(destino)
        return origem.id, destino.id


def _pagar_conta_gerencial(engine, *, tipo: str, valor: float, conta_id: int, data: date) -> None:
    """Simula um lançamento já baixado (pago/recebido) numa conta corrente —
    é o jeito que ContaGerencial.conta_bancaria é preenchido de verdade, na
    baixa de um lançamento (ver pagar_lancamento em fazenda/api/routers/financeiro.py)."""
    with Session(engine) as s:
        conta = s.get(ContaCorrente, conta_id)
        s.add(ContaGerencial(
            tipo=tipo, valor_total=valor, valor_pago=valor,
            data_competencia=data, data_pagamento=data,
            conta_bancaria=rotulo_conta_corrente(conta),
            descricao=f"lançamento de teste ({tipo})",
        ))
        s.commit()


class TestSaldoETransferencia:
    def test_transferencia_move_o_saldo_calculado_das_duas_contas(self, client):
        origem_id, destino_id = _criar_contas(client.engine)

        # Origem recebe uma receita de R$ 1000 — saldo esperado: 1000.
        _pagar_conta_gerencial(client.engine, tipo="receita", valor=1000.0, conta_id=origem_id, data=date(2026, 7, 1))

        saldos = {c["id"]: c["saldo"] for c in client.get("/financeiro/contas-correntes").json()}
        assert saldos[origem_id] == 1000.0
        assert saldos[destino_id] == 0.0

        r = client.post("/financeiro/contas-correntes/transferencias", json={
            "conta_origem_id": origem_id, "conta_destino_id": destino_id,
            "valor": 400.0, "data": "2026-07-10", "observacao": "Reforço de caixa",
        })
        assert r.status_code == 201, r.text

        saldos = {c["id"]: c["saldo"] for c in client.get("/financeiro/contas-correntes").json()}
        assert saldos[origem_id] == 600.0
        assert saldos[destino_id] == 400.0

        with Session(client.engine) as s:
            t = s.exec(select(TransferenciaContas)).first()
            assert t is not None
            assert t.conta_origem_id == origem_id
            assert t.conta_destino_id == destino_id
            assert t.valor == 400.0
            assert t.observacao == "Reforço de caixa"

    def test_transferencia_soma_com_despesa_ja_paga_na_conta_destino(self, client):
        origem_id, destino_id = _criar_contas(client.engine)
        _pagar_conta_gerencial(client.engine, tipo="receita", valor=2000.0, conta_id=origem_id, data=date(2026, 7, 1))
        # Destino já tinha uma despesa paga de R$ 300 antes da transferência.
        _pagar_conta_gerencial(client.engine, tipo="despesa", valor=300.0, conta_id=destino_id, data=date(2026, 7, 2))

        client.post("/financeiro/contas-correntes/transferencias", json={
            "conta_origem_id": origem_id, "conta_destino_id": destino_id, "valor": 500.0, "data": "2026-07-11",
        })

        saldos = {c["id"]: c["saldo"] for c in client.get("/financeiro/contas-correntes").json()}
        assert saldos[origem_id] == 1500.0
        assert saldos[destino_id] == 200.0  # -300 + 500

    def test_conta_origem_e_destino_iguais_e_rejeitada(self, client):
        origem_id, _ = _criar_contas(client.engine)
        r = client.post("/financeiro/contas-correntes/transferencias", json={
            "conta_origem_id": origem_id, "conta_destino_id": origem_id, "valor": 100.0, "data": "2026-07-10",
        })
        assert r.status_code == 400

    def test_valor_negativo_ou_zero_e_rejeitado(self, client):
        origem_id, destino_id = _criar_contas(client.engine)
        r = client.post("/financeiro/contas-correntes/transferencias", json={
            "conta_origem_id": origem_id, "conta_destino_id": destino_id, "valor": 0, "data": "2026-07-10",
        })
        assert r.status_code == 400

    def test_conta_inexistente_e_rejeitada(self, client):
        origem_id, _ = _criar_contas(client.engine)
        r = client.post("/financeiro/contas-correntes/transferencias", json={
            "conta_origem_id": origem_id, "conta_destino_id": 9999, "valor": 100.0, "data": "2026-07-10",
        })
        assert r.status_code == 404

    def test_listar_transferencias(self, client):
        origem_id, destino_id = _criar_contas(client.engine)
        client.post("/financeiro/contas-correntes/transferencias", json={
            "conta_origem_id": origem_id, "conta_destino_id": destino_id, "valor": 250.0, "data": "2026-07-15",
        })
        lista = client.get("/financeiro/contas-correntes/transferencias").json()
        assert len(lista) == 1
        assert lista[0]["valor"] == 250.0
        assert lista[0]["conta_origem_id"] == origem_id
        assert lista[0]["conta_destino_id"] == destino_id


class TestTransferenciaForaDoDre:
    def test_transferencia_nao_entra_como_despesa_ou_receita_no_dre(self, client):
        """A transferência é só um movimento de caixa entre contas próprias
        da fazenda — não é despesa nem receita real, então não pode mexer
        no resultado gerencial (DRE)."""
        origem_id, destino_id = _criar_contas(client.engine)
        _pagar_conta_gerencial(client.engine, tipo="receita", valor=2000.0, conta_id=origem_id, data=date(2026, 7, 1))
        _pagar_conta_gerencial(client.engine, tipo="despesa", valor=500.0, conta_id=origem_id, data=date(2026, 7, 2))

        params = {"data_inicio": "2026-07-01", "data_fim": "2026-07-31", "regime": "caixa"}
        antes = client.get("/financeiro/dre", params=params).json()
        assert antes["receitas_total"] == 2000.0
        assert antes["despesas_total"] == 500.0

        r = client.post("/financeiro/contas-correntes/transferencias", json={
            "conta_origem_id": origem_id, "conta_destino_id": destino_id,
            "valor": 900.0, "data": "2026-07-15",
        })
        assert r.status_code == 201

        depois = client.get("/financeiro/dre", params=params).json()
        assert depois["receitas_total"] == 2000.0
        assert depois["despesas_total"] == 500.0
        assert depois["resultado"] == antes["resultado"]

    def test_transferencia_nao_aparece_no_extrato_de_lancamentos(self, client):
        origem_id, destino_id = _criar_contas(client.engine)
        client.post("/financeiro/contas-correntes/transferencias", json={
            "conta_origem_id": origem_id, "conta_destino_id": destino_id, "valor": 300.0, "data": "2026-07-15",
        })
        extrato = client.get("/financeiro/lancamentos").json()
        assert extrato["total"] == 0
        assert extrato["lancamentos"] == []
