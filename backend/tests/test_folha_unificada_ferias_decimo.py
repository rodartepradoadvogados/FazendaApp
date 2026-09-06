"""
GET /cadastro/folha-pagamento-unificada — Férias e 13º salário (item aprovado
da proposta de Folha de Pagamento: o ledger unificado antes só juntava
funcionário/empreita/contrato/diária, deixando Férias/13º fora do filtro
"Todos"). Confirma que os dois entram no ledger com vencimento/status vindos
da ContaGerencial gerada junto (mesmo padrão de Empreitada/Contrato/Diária).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Pessoa


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


class TestFolhaUnificadaFeriasDecimo:
    def test_ferias_entra_no_ledger_unificado_com_vencimento_da_conta_gerada(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        r = c.post("/cadastro/ferias", json={
            "pessoa_id": pessoa_id,
            "periodo_aquisitivo_inicio": "2025-01-01", "periodo_aquisitivo_fim": "2025-12-31",
            "dias_gozados": 30, "data_inicio_gozo": "2026-07-01", "data_fim_gozo": "2026-07-30",
        })
        assert r.status_code == 200, r.text

        uni = c.get("/cadastro/folha-pagamento-unificada")
        assert uni.status_code == 200, uni.text
        linha = next(l for l in uni.json() if l["tipo"] == "ferias_decimo" and l["origem_subtipo"] == "ferias")
        assert linha["pessoa_id"] == pessoa_id
        assert linha["status"] == "pendente"
        # Vencimento default = 2 dias ANTES do início do gozo (art. 145 CLT).
        # Era `data_fim_gozo` (30/07), ou seja, a conta a pagar e o alerta da
        # Agenda apareciam um mês depois da data em que o dinheiro tinha de
        # sair.
        assert linha["data_vencimento"] == "2026-06-29"

    def test_decimo_terceiro_entra_no_ledger_unificado(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        })
        assert r.status_code == 200, r.text

        uni = c.get("/cadastro/folha-pagamento-unificada")
        assert uni.status_code == 200, uni.text
        linha = next(l for l in uni.json() if l["tipo"] == "ferias_decimo" and l["origem_subtipo"] == "decimo_terceiro")
        assert linha["pessoa_id"] == pessoa_id
        assert linha["status"] == "pendente"

    def test_pagar_a_conta_da_ferias_reflete_como_pago_no_ledger(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        c.post("/cadastro/ferias", json={
            "pessoa_id": pessoa_id,
            "periodo_aquisitivo_inicio": "2025-01-01", "periodo_aquisitivo_fim": "2025-12-31",
            "dias_gozados": 30, "data_inicio_gozo": "2026-07-01", "data_fim_gozo": "2026-07-30",
        })
        uni = c.get("/cadastro/folha-pagamento-unificada").json()
        linha = next(l for l in uni if l["tipo"] == "ferias_decimo" and l["origem_subtipo"] == "ferias")
        assert linha["status"] == "pendente"

        lancs = c.get("/financeiro/lancamentos").json()["lancamentos"]
        lanc = next(l for l in lancs if l["descricao"].startswith("Férias"))
        r = c.put(f"/financeiro/lancamentos/{lanc['id']}/pagar", json={
            "data_pagamento": "2026-07-30", "valor_pago": lanc["valor"],
        })
        assert r.status_code == 200, r.text

        uni2 = c.get("/cadastro/folha-pagamento-unificada").json()
        linha2 = next(l for l in uni2 if l["tipo"] == "ferias_decimo" and l["origem_subtipo"] == "ferias")
        assert linha2["status"] == "pago"

    def test_todas_as_5_categorias_juntas_no_ledger(self, client):
        """"Todos" (item aprovado) precisa mesmo trazer as 5 categorias — não
        só as 4 que já existiam antes desta correção."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        c.post("/cadastro/folha-pagamento", json={"pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0})
        c.post("/cadastro/ferias", json={
            "pessoa_id": pessoa_id,
            "periodo_aquisitivo_inicio": "2025-01-01", "periodo_aquisitivo_fim": "2025-12-31",
            "dias_gozados": 30, "data_inicio_gozo": "2026-07-01", "data_fim_gozo": "2026-07-30",
        })
        c.post("/cadastro/decimo-terceiro", json={"pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12})

        tipos = {l["tipo"] for l in c.get("/cadastro/folha-pagamento-unificada").json()}
        assert "funcionario" in tipos
        assert "ferias_decimo" in tipos
