"""
Testes da leitura automática de nota fiscal/recibo (PDF/JPEG/PNG) via IA.
Nunca chama a API de verdade — sempre com o cliente Anthropic mockado.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial


def _resposta_mock(payload: dict, stop_reason: str = "end_turn"):
    bloco = MagicMock()
    bloco.type = "text"
    bloco.text = json.dumps(payload)
    resposta = MagicMock()
    resposta.content = [bloco]
    resposta.stop_reason = stop_reason
    return resposta


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


class TestLerDocumento:
    def test_sem_chave_de_api_retorna_503(self, client, monkeypatch):
        c, engine = client
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = c.post("/financeiro/ler-documento", files={"file": ("nota.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 503
        assert "ANTHROPIC_API_KEY" in r.json()["detail"]

    def test_tipo_de_arquivo_nao_suportado(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        r = c.post("/financeiro/ler-documento", files={"file": ("nota.txt", b"oi", "text/plain")})
        assert r.status_code == 400

    def test_extrai_nota_fiscal(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        payload = {
            "tipo_documento": "nota_fiscal", "fornecedor_cliente": "Agropecuária Central",
            "numero_documento": "1234", "data_emissao": "2026-07-01", "data_pagamento": None,
            "valor_total": 1500.0, "conta_bancaria": None,
            "itens": [{"produto": "Ração concentrada", "quantidade": 500, "valor_unitario": 3.0, "valor_total": 1500.0}],
            "observacao": None,
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(payload)
            r = c.post("/financeiro/ler-documento", files={"file": ("nota.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 200
        d = r.json()
        assert d["tipo_documento"] == "nota_fiscal"
        assert d["fornecedor_cliente"] == "Agropecuária Central"
        assert d["itens"][0]["produto"] == "Ração concentrada"

    def test_extrai_recibo(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        payload = {
            "tipo_documento": "recibo", "fornecedor_cliente": "João da Silva",
            "numero_documento": None, "data_emissao": None, "data_pagamento": "2026-07-05",
            "valor_total": 300.0, "conta_bancaria": "Banco do Brasil ag 3775-3 cc 3.615-3",
            "itens": [], "observacao": "PIX enviado",
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(payload)
            r = c.post("/financeiro/ler-documento", files={"file": ("recibo.jpg", b"\xff\xd8\xff", "image/jpeg")})
        assert r.status_code == 200
        d = r.json()
        assert d["tipo_documento"] == "recibo"
        assert d["data_pagamento"] == "2026-07-05"

    def test_recusa_da_ia_vira_erro_400(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock({}, stop_reason="refusal")
            r = c.post("/financeiro/ler-documento", files={"file": ("nota.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 400
