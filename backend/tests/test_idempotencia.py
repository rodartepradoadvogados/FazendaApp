"""
Idempotência de POST/PUT/PATCH via header `Idempotency-Key` (middleware
`_idempotencia` em main.py) — protege a fila offline do app de campo
(frontend/lib/offline.ts) contra duplicar um lançamento quando o POST chega
ao servidor mas a resposta se perde por queda de conexão: o cliente reenvia
com a MESMA chave, e o servidor devolve a resposta já processada em vez de
rodar a rota de novo.

Usa POST /alimentacao/analise-bromatologica como endpoint de exemplo (já
coberto em test_alimentacao.py) — a idempotência é um mecanismo genérico do
middleware, não específico deste endpoint.
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import AnaliseBromatologica, IdempotenciaChave

CAMINHO = "/alimentacao/analise-bromatologica"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    lock_conexao = threading.Lock()

    def _get_session_override():
        with lock_conexao, Session(engine) as session:
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


def _contar(engine, modelo) -> int:
    with Session(engine) as s:
        return len(s.exec(select(modelo)).all())


class TestIdempotencia:
    def test_reenvio_com_mesma_chave_nao_duplica(self, client):
        c, engine = client
        corpo = {"data": "2026-07-01", "alimento": "Silagem de milho", "ms_pct": 34.5}

        r1 = c.post(CAMINHO, json=corpo, headers={"Idempotency-Key": "abc123"})
        assert r1.status_code == 201
        r2 = c.post(CAMINHO, json=corpo, headers={"Idempotency-Key": "abc123"})
        assert r2.status_code == 201
        assert r2.json() == r1.json()  # mesma resposta, não uma nova (ids iguais)

        assert _contar(engine, AnaliseBromatologica) == 1
        assert _contar(engine, IdempotenciaChave) == 1

    def test_mesma_chave_payload_diferente_devolve_a_resposta_cacheada(self, client):
        c, engine = client
        r1 = c.post(CAMINHO, json={"data": "2026-07-01", "alimento": "Silagem"}, headers={"Idempotency-Key": "xyz"})
        assert r1.status_code == 201
        r2 = c.post(CAMINHO, json={"data": "2026-07-02", "alimento": "Ração"}, headers={"Idempotency-Key": "xyz"})
        assert r2.status_code == 201
        # A chave manda, não o corpo — segunda resposta é a MESMA da primeira,
        # mesmo com um payload totalmente diferente.
        assert r2.json() == r1.json()
        assert r2.json()["alimento"] == "Silagem"
        assert _contar(engine, AnaliseBromatologica) == 1

    def test_sem_header_nao_usa_cache_duas_chamadas_criam_dois_registros(self, client):
        c, engine = client
        corpo = {"data": "2026-07-01", "alimento": "Silagem"}
        r1 = c.post(CAMINHO, json=corpo)
        r2 = c.post(CAMINHO, json=corpo)
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]
        assert _contar(engine, AnaliseBromatologica) == 2
        assert _contar(engine, IdempotenciaChave) == 0

    def test_erro_de_validacao_nao_fica_em_cache(self, client):
        c, engine = client
        r1 = c.post(CAMINHO, json={"data": "2026-07-01", "alimento": "   "}, headers={"Idempotency-Key": "retry1"})
        assert r1.status_code == 400
        assert _contar(engine, IdempotenciaChave) == 0

        # Mesma chave, payload corrigido — processa normalmente (não trava no erro antigo).
        r2 = c.post(CAMINHO, json={"data": "2026-07-01", "alimento": "Silagem"}, headers={"Idempotency-Key": "retry1"})
        assert r2.status_code == 201
        assert _contar(engine, AnaliseBromatologica) == 1
        assert _contar(engine, IdempotenciaChave) == 1


class TestIdempotenciaFinanceiro:
    """#69 — o frontend desktop (criarLancamentoFinanceiro/marcarPagoFinanceiro
    em lib/api.ts) agora manda Idempotency-Key nesses dois endpoints
    (double-click/retry de rede podia duplicar a nota inteira, ou duplicar
    parcelas de diferença ao pagar). O middleware já é genérico — este teste
    só confirma que os dois endpoints específicos ficam protegidos."""

    def test_criar_lancamento_com_mesma_chave_nao_duplica_a_nota(self, client):
        c, engine = client
        from fazenda.models import ContaGerencial

        corpo = {
            "tipo": "despesa",
            "itens": [{"produto": "Ração", "valor_total": 500.0}],
            "centro_custo": "Pecuária Leiteira",
            "data_emissao": "2026-07-01",
        }
        r1 = c.post("/financeiro/lancamentos", json=corpo, headers={"Idempotency-Key": "nota-1"})
        assert r1.status_code == 201, r1.text
        r2 = c.post("/financeiro/lancamentos", json=corpo, headers={"Idempotency-Key": "nota-1"})
        assert r2.status_code == 201
        assert r2.json() == r1.json()
        assert _contar(engine, ContaGerencial) == 1

    def test_pagar_lancamento_com_mesma_chave_nao_reaplica_o_pagamento(self, client):
        c, engine = client
        from fazenda.models import ContaGerencial

        criado = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração", "valor_total": 500.0}],
            "centro_custo": "Pecuária Leiteira",
            "data_emissao": "2026-07-01",
        })
        assert criado.status_code == 201, criado.text
        lancamento_id = criado.json()["ids"][0]

        pagamento = {"data_pagamento": "2026-07-05", "valor_pago": 500.0}
        r1 = c.put(f"/financeiro/lancamentos/{lancamento_id}/pagar", json=pagamento, headers={"Idempotency-Key": "pg-1"})
        assert r1.status_code == 200, r1.text
        r2 = c.put(f"/financeiro/lancamentos/{lancamento_id}/pagar", json=pagamento, headers={"Idempotency-Key": "pg-1"})
        assert r2.status_code == 200
        assert r2.json() == r1.json()
        assert _contar(engine, ContaGerencial) == 1
