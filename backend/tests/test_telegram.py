"""
Robô do Telegram: fluxo documento → pergunta receita/despesa → lançamento.
As chamadas de rede ao Telegram e a leitura do documento são simuladas.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers import telegram
from fazenda.config import settings
from fazenda.models import ContaGerencial, TelegramPendente

SECRET = "segredo-teste"
CHAT = 123456


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    # Liga o bot e libera o chat de teste.
    monkeypatch.setattr(settings, "telegram_bot_token", "token-teste")
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_allowed_chat_ids", str(CHAT))

    # Simula as chamadas de rede ao Telegram (send/answer) capturando o que sairia.
    enviados: list[dict] = []
    monkeypatch.setattr(telegram, "_tg", lambda metodo, payload: (enviados.append({"metodo": metodo, **payload}) or {"ok": True}))
    # Simula a leitura do documento (sem baixar nem chamar IA).
    monkeypatch.setattr(telegram, "_ler_documento_pendente", lambda pend: {
        "tipo_documento": "nota_fiscal",
        "fornecedor_cliente": "Casa do Produtor",
        "numero_documento": "NF-777",
        "data_emissao": "2026-07-05",
        "data_pagamento": None,
        "valor_total": 250.0,
        "conta_bancaria": None,
        "itens": [{"produto": "Ração", "quantidade": 5, "valor_unitario": 50.0, "valor_total": 250.0}],
        "observacao": None,
    })

    with TestClient(main.app) as c:
        yield c, engine, enviados
    main.app.dependency_overrides.clear()


def _hdr():
    return {"X-Telegram-Bot-Api-Secret-Token": SECRET}


def test_documento_pergunta_e_lanca_despesa(client):
    c, engine, enviados = client
    # 1) Chega um XML → deve criar um pendente e perguntar receita/despesa com botões.
    upd_msg = {"message": {"chat": {"id": CHAT}, "document": {"file_id": "FID1", "file_name": "nota.xml", "mime_type": "text/xml"}}}
    r = c.post("/telegram/webhook", json=upd_msg, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        pend = s.exec(select(TelegramPendente)).first()
        assert pend is not None and pend.kind == "xml"
        pid = pend.id
    assert any(e["metodo"] == "sendMessage" and "reply_markup" in e for e in enviados)

    # 2) Usuário toca em "Despesa" → cria o lançamento e apaga o pendente.
    upd_cb = {"callback_query": {"id": "cb1", "message": {"chat": {"id": CHAT}}, "data": f"lanc:{pid}:despesa"}}
    r = c.post("/telegram/webhook", json=upd_cb, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial)).first()
        assert conta is not None
        assert conta.tipo == "despesa"
        assert conta.origem == "telegram"
        assert conta.valor_total == 250.0
        assert conta.data_pagamento is None  # nota fiscal nasce em aberto
        assert s.exec(select(TelegramPendente)).first() is None  # pendente consumido


def test_chat_nao_liberado_nao_lanca(client, monkeypatch):
    c, engine, enviados = client
    monkeypatch.setattr(settings, "telegram_allowed_chat_ids", "999")  # CHAT não está liberado
    upd = {"message": {"chat": {"id": CHAT}, "document": {"file_id": "FID2", "file_name": "x.xml", "mime_type": "text/xml"}}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None  # nada guardado


def test_webhook_rejeita_segredo_errado(client):
    c, _, _ = client
    r = c.post("/telegram/webhook", json={"message": {}}, headers={"X-Telegram-Bot-Api-Secret-Token": "errado"})
    assert r.status_code == 403
