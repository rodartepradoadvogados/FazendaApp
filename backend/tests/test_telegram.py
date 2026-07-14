"""
Robô do Telegram: fluxo documento → pergunta receita/despesa → lançamento.
As chamadas de rede ao Telegram e a leitura do documento são simuladas.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers import telegram
from fazenda.auth import get_current_user
from fazenda.config import settings
from fazenda.models import ContaGerencial, Fornecedor, LancamentoPendente, TelegramPendente, Usuario

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


def _criar_admin(engine) -> Usuario:
    with Session(engine) as s:
        user = Usuario(username="admin-teste", nome="Admin", senha_hash="x", papel="admin")
        s.add(user)
        s.commit()
        s.refresh(user)
        s.expunge(user)
        return user


def test_documento_pergunta_e_lanca_despesa(client):
    """O lançamento financeiro do robô NUNCA materializa direto — sempre vira
    um LancamentoPendente aguardando aprovação, igual aos lançamentos
    operacionais (pesagem, parto, etc.)."""
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

    # 2) Usuário toca em "Despesa" → cria um LancamentoPendente (fila de
    # aprovação), NÃO um lançamento de verdade, e apaga o pendente do documento.
    upd_cb = {"callback_query": {"id": "cb1", "message": {"chat": {"id": CHAT}}, "data": f"lanc:{pid}:despesa"}}
    r = c.post("/telegram/webhook", json=upd_cb, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(ContaGerencial)).first() is None  # nada lançado de verdade ainda
        assert s.exec(select(TelegramPendente)).first() is None  # pendente do documento consumido
        pendente = s.exec(select(LancamentoPendente)).first()
        assert pendente is not None
        assert pendente.tipo == "despesa"
        assert pendente.status == "pendente"
        dados = json.loads(pendente.payload)
        assert dados["fornecedor_cliente"] == "Casa do Produtor"
        assert dados["valor_total"] == 250.0

    # 3) Aprovar sem o fornecedor cadastrado deve FALHAR (e não criar nada) —
    # este é o bug relatado: "Comercial Montividiu" nunca tinha sido cadastrado.
    import main
    admin = _criar_admin(engine)
    main.app.dependency_overrides[get_current_user] = lambda: admin
    r = c.post(f"/aprovacoes/{pendente.id}/aprovar")
    assert r.status_code == 400
    assert "não está cadastrado" in r.json()["detail"]
    with Session(engine) as s:
        assert s.exec(select(ContaGerencial)).first() is None
        p = s.get(LancamentoPendente, pendente.id)
        assert p.status == "pendente"  # continua pendente, não vira "aprovado" sozinho
        assert p.erro  # erro fica registrado para o admin ver na tela

    # 4) Cadastrando o fornecedor e aprovando de novo agora materializa de verdade.
    with Session(engine) as s:
        s.add(Fornecedor(nome="Casa do Produtor", tipo="fornecedor"))
        s.commit()
    r = c.post(f"/aprovacoes/{pendente.id}/aprovar")
    assert r.status_code == 200
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial)).first()
        assert conta is not None
        assert conta.tipo == "despesa"
        assert conta.origem == "telegram"
        assert conta.valor_total == 250.0
        assert conta.data_pagamento is None  # nota fiscal nasce em aberto
        p = s.get(LancamentoPendente, pendente.id)
        assert p.status == "aprovado"


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


def test_pdf_sem_mime_type_correto_ainda_e_reconhecido(client):
    """Alguns clientes do Telegram enviam PDF sem preencher mime_type (ou com
    um valor genérico) — antes, isso fazia o arquivo ser descartado em
    silêncio; agora cai no fallback pela extensão .pdf, igual ao XML."""
    c, engine, enviados = client
    upd = {"message": {"chat": {"id": CHAT}, "document": {
        "file_id": "FID-PDF", "file_name": "nota_fiscal.pdf", "mime_type": "application/octet-stream",
    }}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        pend = s.exec(select(TelegramPendente)).first()
        assert pend is not None and pend.kind == "documento"
    assert any(e["metodo"] == "sendMessage" and "reply_markup" in e for e in enviados)


def test_arquivo_tipo_nao_reconhecido_avisa_usuario(client):
    """Um arquivo que não é XML/PDF/JPG/PNG nem por mime nem por extensão deve
    avisar o usuário, não cair na mensagem genérica de comando (como se nada
    tivesse sido enviado)."""
    c, engine, enviados = client
    upd = {"message": {"chat": {"id": CHAT}, "document": {
        "file_id": "FID-ZIP", "file_name": "arquivo.zip", "mime_type": "application/zip",
    }}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None
    ultima = enviados[-1]
    assert "não reconheci" in ultima["text"].lower()
