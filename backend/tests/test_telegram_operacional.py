"""
Lançamentos operacionais pelo Telegram → fila de aprovação → materialização.
As chamadas de rede ao Telegram são simuladas.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers import telegram
from fazenda.config import settings
from fazenda.models import ControleLeiteiro, LancamentoPendente, Lote, Secagem

SECRET = "seg"
CHAT = 42


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Lote(codigo="02", nome="Lactação alta"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _Admin:
        id = 1
        username = "AlexandreRodarte"
        papel = "admin"
        ativo = True

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _Admin()

    monkeypatch.setattr(settings, "telegram_bot_token", "tok")
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_allowed_chat_ids", str(CHAT))
    enviados: list[dict] = []
    monkeypatch.setattr(telegram, "_tg", lambda m, p: (enviados.append({"m": m, **p}) or {"ok": True}))

    with TestClient(main.app) as c:
        yield c, engine, enviados
    main.app.dependency_overrides.clear()


def _hdr():
    return {"X-Telegram-Bot-Api-Secret-Token": SECRET}


def _msg(c, texto):
    return c.post("/telegram/webhook", json={"message": {"chat": {"id": CHAT}, "from": {"first_name": "Zé"}, "text": texto}}, headers=_hdr())


def _cb(c, data):
    return c.post("/telegram/webhook", json={"callback_query": {"id": "x", "from": {"first_name": "Zé"}, "message": {"chat": {"id": CHAT}}, "data": data}}, headers=_hdr())


def test_fluxo_controle_leiteiro_ate_aprovacao(ctx):
    c, engine, _ = ctx
    _msg(c, "/lancar")
    _cb(c, "flow:controle_leiteiro")   # inicia
    _msg(c, "1234")                     # numero_matriz
    _msg(c, "hoje")                     # data
    _msg(c, "20 18 15")                # ordenhas → finaliza

    with Session(engine) as s:
        pend = s.exec(select(LancamentoPendente)).first()
        assert pend is not None
        assert pend.tipo == "controle_leiteiro"
        assert pend.status == "pendente"
        assert pend.solicitante_nome == "Zé"
        dados = json.loads(pend.payload)
        assert dados["numero_matriz"] == "1234"
        assert dados["ordenhas"] == [20.0, 18.0, 15.0]
        pid = pend.id

    # Admin vê na fila.
    r = c.get("/aprovacoes")
    assert r.status_code == 200 and len(r.json()) == 1

    # Aprova → cria o ControleLeiteiro real.
    r = c.post(f"/aprovacoes/{pid}/aprovar")
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        cl = s.exec(select(ControleLeiteiro)).first()
        assert cl is not None
        assert cl.numero_matriz == "1234"
        assert cl.producao_kg == 53.0  # 20+18+15
        assert s.get(LancamentoPendente, pid).status == "aprovado"


def test_fluxo_secagem_com_botao_e_rejeitar(ctx):
    c, engine, _ = ctx
    _cb(c, "flow:secagem")
    _msg(c, "0777")                    # numero_matriz
    _msg(c, "10/07/2026")             # data
    _cb(c, "ans:3")                    # motivo (índice 3 = "mastite")

    with Session(engine) as s:
        pend = s.exec(select(LancamentoPendente)).first()
        assert pend and pend.tipo == "secagem"
        assert json.loads(pend.payload)["motivo"] == "mastite"
        pid = pend.id

    # Rejeita → nada é criado.
    r = c.post(f"/aprovacoes/{pid}/rejeitar")
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Secagem)).first() is None
        assert s.get(LancamentoPendente, pid).status == "rejeitado"
    # Some da fila de pendentes.
    assert c.get("/aprovacoes").json() == []


def test_contagem_pendentes(ctx):
    c, engine, _ = ctx
    _cb(c, "flow:controle_leiteiro")
    _msg(c, "1")
    _msg(c, "hoje")
    _msg(c, "10")
    assert c.get("/aprovacoes/contagem").json()["pendentes"] == 1


def test_sanidade_unidade_por_botao_e_editar_pendente(ctx):
    c, engine, _ = ctx
    _cb(c, "flow:sanidade")
    _msg(c, "403")            # animais
    _msg(c, "11/07/2026")     # data
    _msg(c, "Borgal")         # produto
    _msg(c, "40")             # quantidade
    _cb(c, "ans:0")           # unidade por botão (índice 0 = "ml") → finaliza

    with Session(engine) as s:
        pend = s.exec(select(LancamentoPendente)).first()
        assert pend and pend.tipo == "sanidade"
        dados = json.loads(pend.payload)
        assert dados["unidade"] == "ml"      # veio da lista, não texto livre
        pid = pend.id

    # Editar a pendência (corrigir o produto) antes de aprovar.
    novos = {**dados, "produto": "Borgal SC"}
    r = c.put(f"/aprovacoes/{pid}", json={"dados": novos})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert json.loads(s.get(LancamentoPendente, pid).payload)["produto"] == "Borgal SC"


def test_erro_ao_processar_nao_trava_webhook(ctx, monkeypatch):
    """Um erro ao tratar a mensagem deve responder 200 (para não travar a fila
    do Telegram) e avisar o usuário com o detalhe técnico."""
    c, _, enviados = ctx
    def _explode(*a, **k):
        raise RuntimeError("boom-de-teste")
    monkeypatch.setattr(telegram, "_tratar_mensagem", _explode)
    r = _msg(c, "/lancar")
    assert r.status_code == 200  # nunca 500 — não trava a fila
    assert any("boom-de-teste" in (e.get("text") or "") for e in enviados)
