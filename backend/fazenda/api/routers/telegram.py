"""
Robô do Telegram — intake de documentos financeiros.

O usuário manda um XML de NF-e, uma foto/PDF de nota fiscal ou um recibo/
comprovante para o robô. O robô pergunta, com botões, se é RECEITA ou DESPESA;
ao responder, lê o documento com a mesma leitura automática do site
(`parse_nfe_xml` para XML, `ler_documento`/IA para foto/PDF) e cria o
lançamento em Contas a pagar/receber (ou pagas/recebidas, se for recibo já
quitado), deixando-o pendente de conferência e edição no site.

Ligado só quando `TELEGRAM_BOT_TOKEN` está configurado. As chamadas do Telegram
chegam no webhook `/telegram/webhook` (rota pública, validada pelo segredo
`X-Telegram-Bot-Api-Secret-Token`). Só os chats liberados em
`TELEGRAM_ALLOWED_CHAT_IDS` conseguem lançar — os demais recebem o próprio id
para pedir liberação ao administrador.
"""
from __future__ import annotations

from datetime import date, datetime

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlmodel import Session, select

from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import TelegramPendente

router = APIRouter(prefix="/telegram", tags=["telegram"])

TG_API = "https://api.telegram.org"
MIME_DOCUMENTO = {"application/pdf", "image/jpeg", "image/png"}


# ── Infra do Telegram (chamadas à API do bot) ──────────────────────────────
def _token() -> str:
    if not settings.telegram_bot_token:
        raise RuntimeError("Robô do Telegram desligado (TELEGRAM_BOT_TOKEN não configurado).")
    return settings.telegram_bot_token


def _tg(metodo: str, payload: dict) -> dict:
    """Chama um método da Bot API (sendMessage, answerCallbackQuery, etc.)."""
    try:
        r = httpx.post(f"{TG_API}/bot{_token()}/{metodo}", json=payload, timeout=20)
        return r.json()
    except Exception:
        return {"ok": False}


def _enviar(chat_id: int, texto: str, botoes: list[list[dict]] | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}
    if botoes:
        payload["reply_markup"] = {"inline_keyboard": botoes}
    _tg("sendMessage", payload)


def _responder_callback(callback_id: str, texto: str = "") -> None:
    _tg("answerCallbackQuery", {"callback_query_id": callback_id, "text": texto})


def _baixar_arquivo(file_id: str) -> bytes:
    """getFile + download do conteúdo do arquivo pelo file_id."""
    info = httpx.get(f"{TG_API}/bot{_token()}/getFile", params={"file_id": file_id}, timeout=20).json()
    if not info.get("ok"):
        raise RuntimeError("Não consegui localizar o arquivo no Telegram.")
    caminho = info["result"]["file_path"]
    return httpx.get(f"{TG_API}/file/bot{_token()}/{caminho}", timeout=60).content


# ── Autorização ────────────────────────────────────────────────────────────
def _chats_liberados() -> set[int]:
    ids = set()
    for parte in (settings.telegram_allowed_chat_ids or "").split(","):
        parte = parte.strip()
        if parte:
            try:
                ids.add(int(parte))
            except ValueError:
                pass
    return ids


def _autorizado(chat_id: int) -> bool:
    liberados = _chats_liberados()
    return bool(liberados) and chat_id in liberados


# ── Conversão do documento lido em lançamento financeiro ───────────────────
def _parse_data(valor) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _criar_lancamento_do_documento(session: Session, dados: dict, tipo: str) -> dict:
    """Monta um LancamentoIn a partir do documento lido e grava usando a mesma
    lógica do site. `tipo` é a escolha do usuário: 'receita' ou 'despesa'."""
    # Importado aqui para evitar import circular (financeiro importa muita coisa).
    from fazenda.api.routers.financeiro import ItemIn, LancamentoIn, criar_lancamento

    itens_doc = dados.get("itens") or []
    itens: list[ItemIn] = []
    for it in itens_doc:
        produto = (it.get("produto") or "").strip()
        if not produto:
            continue
        vt = it.get("valor_total")
        if vt is None and it.get("quantidade") and it.get("valor_unitario"):
            vt = round(it["quantidade"] * it["valor_unitario"], 2)
        itens.append(ItemIn(
            produto=produto,
            quantidade=it.get("quantidade"),
            valor_unitario=it.get("valor_unitario"),
            valor_total=float(vt or 0),
        ))
    if not itens:
        # Sem itens discriminados: um único item com o valor total do documento.
        rotulo = (dados.get("fornecedor_cliente") or "Documento recebido pelo Telegram").strip()
        itens = [ItemIn(produto=rotulo, valor_total=float(dados.get("valor_total") or 0))]

    eh_recibo = dados.get("tipo_documento") == "recibo"
    data_emissao = _parse_data(dados.get("data_emissao"))
    data_pagamento = _parse_data(dados.get("data_pagamento")) if eh_recibo else None
    valor_total = sum(i.valor_total for i in itens)

    lanc = LancamentoIn(
        tipo=tipo,
        itens=itens,
        fornecedor_cliente=dados.get("fornecedor_cliente"),
        numero_documento=dados.get("numero_documento"),
        tipo_documento="Nota fiscal" if not eh_recibo else "Recibo/comprovante",
        data_emissao=data_emissao,
        # Vencimento alimenta Contas a pagar/receber e a Agenda.
        data_vencimento=data_emissao or data_pagamento,
        # Recibo já quitado nasce pago (vai para Contas pagas/recebidas).
        data_pagamento=data_pagamento,
        valor_pago=valor_total if data_pagamento else None,
        conta_bancaria=dados.get("conta_bancaria") if eh_recibo else None,
    )
    res = criar_lancamento(dados=lanc, session=session)
    # Marca a origem "telegram" (LancamentoIn não carrega esse campo) para
    # identificar os lançamentos que vieram pelo robô.
    from fazenda.models import ContaGerencial
    for cid in res.get("ids", []):
        conta = session.get(ContaGerencial, cid)
        if conta:
            conta.origem = "telegram"
            session.add(conta)
    session.commit()
    return res


def _ler_documento_pendente(pend: TelegramPendente) -> dict:
    conteudo = _baixar_arquivo(pend.file_id)
    if pend.kind == "xml":
        from fazenda.rules.nfe_xml import parse_nfe_xml
        dados = parse_nfe_xml(conteudo.decode("utf-8", errors="replace"))
        dados.setdefault("tipo_documento", "nota_fiscal")
        return dados
    from fazenda.rules.leitura_documento import ler_documento
    return ler_documento(conteudo, pend.mime or "application/pdf")


# ── Webhook ────────────────────────────────────────────────────────────────
@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    session: Session = Depends(get_session),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    # Segurança: só aceita chamadas que trazem o segredo combinado no setWebhook.
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Segredo inválido")

    update = await request.json()

    # 1) Clique num botão (receita/despesa/cancelar).
    if "callback_query" in update:
        _tratar_callback(session, update["callback_query"])
        return {"ok": True}

    # 2) Mensagem (documento/foto ou comando).
    msg = update.get("message") or update.get("edited_message")
    if msg:
        _tratar_mensagem(session, msg)
    return {"ok": True}


def _tratar_mensagem(session: Session, msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    texto = (msg.get("text") or "").strip().lower()

    if texto in ("/start", "/id", "/meuid", "meu id", "id"):
        _enviar(chat_id, (
            "👋 Sou o robô financeiro da fazenda.\n\n"
            f"O <b>id deste chat</b> é <code>{chat_id}</code>.\n"
            "Peça ao administrador para liberar este id e depois é só me mandar "
            "o XML, a foto/PDF da nota fiscal ou o recibo/comprovante."
        ))
        return

    # Extrai o arquivo: documento (.xml/.pdf/imagem) ou foto.
    file_id = file_name = mime = kind = None
    if "document" in msg:
        doc = msg["document"]
        file_id = doc["file_id"]
        file_name = doc.get("file_name")
        mime = doc.get("mime_type")
        nome_l = (file_name or "").lower()
        if mime in ("text/xml", "application/xml") or nome_l.endswith(".xml"):
            kind = "xml"
        elif mime in MIME_DOCUMENTO:
            kind = "documento"
    elif "photo" in msg and msg["photo"]:
        maior = msg["photo"][-1]  # a última é a de maior resolução
        file_id = maior["file_id"]
        mime = "image/jpeg"
        kind = "documento"

    if not file_id or not kind:
        if not _autorizado(chat_id):
            _enviar(chat_id, f"Seu id de chat é <code>{chat_id}</code>. Peça a liberação ao administrador.")
            return
        _enviar(chat_id, (
            "Me envie um <b>XML</b> de nota fiscal, ou uma <b>foto/PDF</b> da nota, "
            "recibo ou comprovante de pagamento — eu preencho o lançamento para você."
        ))
        return

    if not _autorizado(chat_id):
        _enviar(chat_id, (
            "🚫 Este chat ainda não está liberado para lançar.\n"
            f"Seu id é <code>{chat_id}</code> — peça ao administrador para liberá-lo."
        ))
        return

    pend = TelegramPendente(chat_id=chat_id, file_id=file_id, file_name=file_name, mime=mime, kind=kind)
    session.add(pend)
    session.commit()
    session.refresh(pend)

    _enviar(chat_id,
        "📄 Recebi o documento. Este lançamento é <b>receita</b> ou <b>despesa</b>?",
        botoes=[[
            {"text": "🧾 Despesa", "callback_data": f"lanc:{pend.id}:despesa"},
            {"text": "💰 Receita", "callback_data": f"lanc:{pend.id}:receita"},
        ], [
            {"text": "✖️ Cancelar", "callback_data": f"cancel:{pend.id}"},
        ]],
    )


def _tratar_callback(session: Session, cq: dict) -> None:
    callback_id = cq["id"]
    chat_id = cq["message"]["chat"]["id"]
    data = cq.get("data") or ""
    partes = data.split(":")
    acao = partes[0] if partes else ""
    pid = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else None

    _responder_callback(callback_id)
    if not _autorizado(chat_id):
        _enviar(chat_id, "🚫 Chat não liberado.")
        return

    pend = session.get(TelegramPendente, pid) if pid else None
    if not pend or pend.chat_id != chat_id:
        _enviar(chat_id, "Não encontrei este documento (pode já ter sido tratado). Envie de novo, por favor.")
        return

    if acao == "cancel":
        session.delete(pend)
        session.commit()
        _enviar(chat_id, "✖️ Cancelado. O documento não foi lançado.")
        return

    if acao == "lanc":
        tipo = partes[2] if len(partes) > 2 else ""
        if tipo not in ("receita", "despesa"):
            _enviar(chat_id, "Não entendi a escolha. Envie o documento de novo.")
            return
        _enviar(chat_id, "⏳ Lendo o documento e lançando…")
        try:
            dados = _ler_documento_pendente(pend)
            res = _criar_lancamento_do_documento(session, dados, tipo)
        except RuntimeError as e:
            _enviar(chat_id, f"⚠️ {e}")
            return
        except Exception as e:  # noqa: BLE001 — mensagem amigável, erro logado pela stack
            _enviar(chat_id, f"⚠️ Não consegui ler o documento: {e}")
            return
        finally:
            session.delete(pend)
            session.commit()

        eh_recibo = dados.get("tipo_documento") == "recibo"
        destino = ("Contas recebidas" if eh_recibo else "Contas a receber") if tipo == "receita" \
            else ("Contas pagas" if eh_recibo else "Contas a pagar")
        forn = dados.get("fornecedor_cliente") or "—"
        valor = res.get("valor_liquido") or 0
        _enviar(chat_id, (
            f"✅ Lançado em <b>{destino}</b>.\n"
            f"Nº do lançamento: <code>{res.get('numero_lancamento')}</code>\n"
            f"Contraparte: {forn}\n"
            f"Valor: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + "\n\n"
            "Está <b>pendente de conferência</b> — abra o site em "
            "Financeiro → " + destino + " e use <b>Editar</b> para revisar e salvar."
        ))


# ── Registro do webhook (chamado no startup) ───────────────────────────────
def registrar_webhook_telegram() -> None:
    """Aponta o Telegram para o nosso webhook. Idempotente e silencioso —
    nunca derruba o startup se algo falhar."""
    if not settings.telegram_bot_token:
        return
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        return
    try:
        payload = {
            "url": f"{base}/telegram/webhook",
            "allowed_updates": ["message", "callback_query"],
        }
        if settings.telegram_webhook_secret:
            payload["secret_token"] = settings.telegram_webhook_secret
        httpx.post(f"{TG_API}/bot{settings.telegram_bot_token}/setWebhook", json=payload, timeout=20)
    except Exception:
        pass


@router.get("/status")
def telegram_status() -> dict:
    """Diagnóstico rápido (sem expor o token) — útil para o administrador."""
    return {
        "ligado": bool(settings.telegram_bot_token),
        "webhook_base": settings.public_base_url or None,
        "chats_liberados": sorted(_chats_liberados()),
        "segredo_configurado": bool(settings.telegram_webhook_secret),
    }
