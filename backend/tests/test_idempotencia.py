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


@pytest.fixture
def client_com_get_session_real(monkeypatch):
    """Variante do fixture `client` que NÃO sobrescreve `database.get_session`
    — só troca o `engine` real por um SQLite descartável. Existe só para o
    teste abaixo: o bug estava no CAMINHO REAL do middleware de idempotência
    (`main.py::_sessao_idempotencia`), que chama `get_session()` direto,
    sem passar pela injeção de dependência do FastAPI — um override de teste
    (como o fixture `client` normal usa) mascara exatamente esse bug, porque
    o override é sempre uma função sem parâmetro nenhum."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


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

    def test_falha_ao_gravar_cache_nao_derruba_a_resposta_ja_processada(self, client, monkeypatch):
        """Bug real relatado pelo usuário (01/09/2026): "Sem conexão com a
        API" ao confirmar um pagamento, mesmo o lançamento tendo sido salvo —
        acontecia sempre, com ou sem anexar comprovante. Causa: o middleware
        só perdoava `IntegrityError` (a corrida esperada entre duas tentativas
        com a mesma chave) ao gravar o CACHE da idempotência — qualquer OUTRO
        erro nesse passo (ex.: uma conexão instável com o Postgres) escapava
        do middleware inteiro, derrubando a resposta que a rota já tinha
        processado com sucesso. Simula esse "qualquer outro erro"."""
        c, engine = client
        from sqlmodel import Session as _SessionCls

        # Quebra só o passo de GRAVAR o cache (session.add com uma
        # IdempotenciaChave) — o SELECT de consulta ao cache, no início do
        # middleware, continua funcionando normalmente, senão o teste nem
        # chegaria a rodar a rota de verdade.
        original_add = _SessionCls.add

        def _add_quebrado(self, instance, *args, **kwargs):
            if isinstance(instance, IdempotenciaChave):
                raise RuntimeError("conexão instável com o Postgres (simulado)")
            return original_add(self, instance, *args, **kwargs)

        monkeypatch.setattr(_SessionCls, "add", _add_quebrado)
        corpo = {"data": "2026-07-01", "alimento": "Silagem"}
        r = c.post(CAMINHO, json=corpo, headers={"Idempotency-Key": "falha-cache-1"})
        # A resposta real (o lançamento JÁ foi salvo pela rota) precisa chegar
        # ao cliente mesmo com o cache de idempotência falhando por baixo.
        assert r.status_code == 201, r.text
        assert _contar(engine, AnaliseBromatologica) == 1
        assert _contar(engine, IdempotenciaChave) == 0  # cache não gravou, e não precisa

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


class TestIdempotenciaMantemCorsHeaders:
    """Bug real relatado pelo usuário (05/09/2026): "Sem conexão com a API"
    em TODA baixa do Financeiro, mesmo com o backend respondendo 200 OK em
    100% das tentativas (confirmado nos logs de produção do Railway — nenhum
    5xx, todas as chamadas HTTP retornam 200). A causa não era rede
    instável: o middleware `_idempotencia` reconstrói a resposta (tanto ao
    gravar o cache de uma resposta nova quanto ao devolver um cache-hit) com
    `Response(content=..., status_code=..., media_type=...)` — um objeto
    novo, sem os headers da resposta original. Como esse middleware é
    registrado por último (vira o mais EXTERNO da pilha — quem `add_middleware`
    insere por último embrulha os demais), a resposta que ele reconstrói é a
    que sai de verdade para o cliente, sem os headers `Access-Control-Allow-*`
    que o CORSMiddleware (registrado antes, portanto mais interno) já tinha
    acrescentado. Sem esses headers, o navegador trata TODA resposta 2xx de
    um POST/PUT/PATCH com `Idempotency-Key` como falha de CORS — `fetch()`
    rejeita com `TypeError: Failed to fetch`, e o frontend traduz isso para
    "Sem conexão com a API" (ver `netError` em lib/api.ts), mesmo com o
    servidor tendo processado e respondido 200 OK. Corrigido registrando o
    CORSMiddleware por ÚLTIMO (torna-se o mais externo de todos, garantindo
    que TUDO que sai — inclusive respostas encurtadas por outros middlewares,
    como o bloqueio de modo suporte — sempre passa pela injeção de CORS)."""

    def test_resposta_nova_com_idempotency_key_mantem_cors(self, client):
        c, _ = client
        r = c.post(
            CAMINHO, json={"data": "2026-07-01", "alimento": "Silagem"},
            headers={"Idempotency-Key": "cors-nova-1", "Origin": "http://localhost:3000"},
        )
        assert r.status_code == 201, r.text
        assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_resposta_em_cache_hit_mantem_cors(self, client):
        c, _ = client
        corpo = {"data": "2026-07-01", "alimento": "Silagem"}
        r1 = c.post(CAMINHO, json=corpo, headers={"Idempotency-Key": "cors-cache-1", "Origin": "http://localhost:3000"})
        assert r1.status_code == 201, r1.text
        assert r1.headers.get("access-control-allow-origin") == "http://localhost:3000"

        # Segunda chamada, mesma chave — cai no caminho de cache-hit (devolve
        # direto, sem chamar a rota de novo) e precisa manter o mesmo header.
        r2 = c.post(CAMINHO, json=corpo, headers={"Idempotency-Key": "cors-cache-1", "Origin": "http://localhost:3000"})
        assert r2.status_code == 201
        assert r2.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestIdempotenciaComGetSessionReal:
    """Bug real relatado pelo usuário (09/09/2026): "Sem conexão com a API"
    ao confirmar um pagamento (PUT /financeiro/lancamentos/{id}/pagar) —
    voltou a acontecer depois do PR #744 (contexto de fazenda por sessão).
    `get_session` ganhou o parâmetro `authorization` (Header do FastAPI, só
    resolvido quando chamado VIA `Depends`), mas `_sessao_idempotencia`
    chama `get_session()` direto — o parâmetro não resolvido fica sendo o
    próprio marcador `Header(...)`, e `get_fazenda_atual_id` quebra em
    `authorization.lower()` (AttributeError: 'Header' object has no
    attribute 'lower'), only com o header `Idempotency-Key` presente em
    POST/PUT/PATCH (por isso passou batido nos outros testes: o fixture
    `client` comum sobrescreve `get_session` por um override sem parâmetro,
    que mascara exatamente este bug)."""

    def test_put_com_idempotency_key_e_authorization_nao_quebra(self, client_com_get_session_real):
        c, _ = client_com_get_session_real
        r = c.post(
            CAMINHO, json={"data": "2026-07-01", "alimento": "Silagem"},
            headers={"Idempotency-Key": "sessao-real-1", "Authorization": "Bearer token-qualquer"},
        )
        assert r.status_code == 201, r.text

    def test_sem_authorization_tambem_nao_quebra(self, client_com_get_session_real):
        c, _ = client_com_get_session_real
        r = c.post(
            CAMINHO, json={"data": "2026-07-01", "alimento": "Silagem"},
            headers={"Idempotency-Key": "sessao-real-2"},
        )
        assert r.status_code == 201, r.text
