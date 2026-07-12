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

import json

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlmodel import Session, select

from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import LancamentoPendente, TelegramPendente, TelegramSessao
from fazenda.rules import telegram_fluxos as fx

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

    # SEMPRE responde 200 ao Telegram, mesmo se der erro ao processar: um erro
    # numa mensagem não pode travar a fila (o Telegram reenvia a mesma update
    # em loop e bloqueia as próximas). Em caso de erro, avisa o usuário com o
    # detalhe técnico — ajuda muito o diagnóstico.
    try:
        if "callback_query" in update:
            _tratar_callback(session, update["callback_query"])
        else:
            msg = update.get("message") or update.get("edited_message")
            if msg:
                _tratar_mensagem(session, msg)
    except Exception as e:  # noqa: BLE001
        try:
            session.rollback()
        except Exception:
            pass
        chat_id = _chat_id_do_update(update)
        if chat_id:
            _enviar(chat_id, f"⚠️ Tive um problema ao processar isso. Detalhe técnico:\n<code>{str(e)[:400]}</code>")
    return {"ok": True}


def _chat_id_do_update(update: dict) -> int | None:
    if "callback_query" in update:
        return (((update["callback_query"] or {}).get("message") or {}).get("chat") or {}).get("id")
    msg = update.get("message") or update.get("edited_message") or {}
    return (msg.get("chat") or {}).get("id")


def _boas_vindas(chat_id: int) -> str:
    return (
        "👋 Sou o robô da fazenda.\n\n"
        f"Id deste chat: <code>{chat_id}</code>.\n\n"
        "• <b>Nota/recibo/comprovante</b> (financeiro): me envie o XML ou a foto/PDF.\n"
        "• <b>Evento de campo</b> (pesagem, parto, secagem, troca de lote…): toque em /lancar.\n"
        "• Cancelar um lançamento em andamento: /cancelar."
    )


def _tratar_mensagem(session: Session, msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    nome = (msg.get("from") or {}).get("first_name")
    texto = (msg.get("text") or "").strip()
    texto_l = texto.lower()

    if texto_l in ("/start", "/id", "/meuid", "meu id", "id", "/ajuda", "ajuda"):
        _enviar(chat_id, _boas_vindas(chat_id))
        return
    if texto_l in ("/cancelar", "cancelar"):
        _cancelar_sessao(session, chat_id)
        _enviar(chat_id, "✖️ Ok, cancelei o lançamento em andamento.")
        return

    # Documento/foto → fluxo financeiro (leitura de nota/recibo).
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

    if file_id and kind:
        if not _autorizado(chat_id):
            _enviar(chat_id, f"🚫 Chat não liberado. Seu id é <code>{chat_id}</code> — peça ao administrador.")
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
        return

    # Sem arquivo: comandos/perguntas do fluxo operacional.
    if not _autorizado(chat_id):
        _enviar(chat_id, f"Seu id de chat é <code>{chat_id}</code>. Peça a liberação ao administrador.")
        return

    if texto_l in ("/lancar", "/lançar", "lancar", "lançar", "/novo", "/menu", "menu"):
        _menu_lancamentos(chat_id)
        return

    sess = _sessao(session, chat_id)
    if sess and sess.fluxo:
        _responder_campo(session, sess, texto=texto, nome=nome)
        return

    _enviar(chat_id, "Para lançar um evento de campo, toque em /lancar. Para uma nota/recibo, me envie o arquivo.")


# ── Motor de conversa (lançamentos operacionais) ───────────────────────────
def _menu_lancamentos(chat_id: int) -> None:
    botoes = [[{"text": f["rotulo"], "callback_data": f"flow:{tipo}"}] for tipo, f in fx.FLUXOS.items()]
    _enviar(chat_id, "O que você quer lançar? (vai para aprovação)", botoes=botoes)


def _sessao(session: Session, chat_id: int) -> TelegramSessao | None:
    return session.exec(select(TelegramSessao).where(TelegramSessao.chat_id == chat_id)).first()


def _cancelar_sessao(session: Session, chat_id: int) -> None:
    sess = _sessao(session, chat_id)
    if sess:
        session.delete(sess)
        session.commit()


def _iniciar_fluxo(session: Session, chat_id: int, tipo: str, nome: str | None) -> None:
    if tipo not in fx.FLUXOS:
        _enviar(chat_id, "Lançamento desconhecido. Toque em /lancar.")
        return
    sess = _sessao(session, chat_id) or TelegramSessao(chat_id=chat_id)
    sess.fluxo = tipo
    sess.etapa = 0
    sess.dados = json.dumps({"_nome": nome} if nome else {})
    sess.atualizado_em = datetime.utcnow()
    session.add(sess)
    session.commit()
    session.refresh(sess)
    _perguntar_campo(session, sess)


def _perguntar_campo(session: Session, sess: TelegramSessao) -> None:
    campos = fx.FLUXOS[sess.fluxo]["campos"]
    if sess.etapa >= len(campos):
        _finalizar(session, sess)
        return
    campo = campos[sess.etapa]
    if campo["tipo"] == "opcoes":
        opcoes = campo["opcoes"](session) if callable(campo["opcoes"]) else campo["opcoes"]
        dados = json.loads(sess.dados)
        dados["_ops"] = opcoes
        sess.dados = json.dumps(dados)
        session.add(sess)
        session.commit()
        botoes = [[{"text": rot, "callback_data": f"ans:{i}"}] for i, (_val, rot) in enumerate(opcoes)]
        if not campo["obrigatorio"]:
            botoes.append([{"text": "⏭️ Pular", "callback_data": "ans:-1"}])
        botoes.append([{"text": "✖️ Cancelar", "callback_data": "flowcancel"}])
        _enviar(sess.chat_id, campo["pergunta"], botoes=botoes)
    else:
        _enviar(sess.chat_id, campo["pergunta"])


def _responder_campo(session: Session, sess: TelegramSessao, texto: str | None = None, idx: int | None = None, nome: str | None = None) -> None:
    chat_id = sess.chat_id
    campos = fx.FLUXOS[sess.fluxo]["campos"]
    if sess.etapa >= len(campos):
        _finalizar(session, sess)
        return
    campo = campos[sess.etapa]
    dados = json.loads(sess.dados)
    tp = campo["tipo"]

    if tp == "opcoes":
        if idx is None:
            _enviar(chat_id, "Toque em um dos botões, por favor.")
            return
        if idx == -1:
            dados.pop(campo["chave"], None)
        else:
            ops = dados.get("_ops") or []
            if idx < 0 or idx >= len(ops):
                _enviar(chat_id, "Opção inválida. Tente de novo.")
                return
            dados[campo["chave"]] = ops[idx][0]
        dados.pop("_ops", None)
    else:
        val = (texto or "").strip()
        low = val.lower()
        if not campo["obrigatorio"] and low in ("pular", "-", ""):
            dados.pop(campo["chave"], None)
        elif tp == "animal":
            if not fx.animal_existe(session, val):
                _enviar(chat_id, f"⚠️ Não achei o animal <b>{val}</b> no rebanho — registro assim mesmo; confira na aprovação.")
            dados[campo["chave"]] = val
        elif tp == "numeros":
            lista = fx._lista(val)
            if not lista:
                _enviar(chat_id, "Informe ao menos um número.")
                return
            faltantes = [n for n in lista if not fx.animal_existe(session, n)]
            if faltantes:
                _enviar(chat_id, f"⚠️ Não achei: {', '.join(faltantes)} — registro assim mesmo.")
            dados[campo["chave"]] = lista
        elif tp == "numero":
            try:
                dados[campo["chave"]] = float(val.replace(",", "."))
            except ValueError:
                _enviar(chat_id, "Valor inválido. Digite um número (ex.: 12,5).")
                return
        elif tp == "data":
            d = fx.parse_data_br(val, date.today())
            if not d:
                _enviar(chat_id, "Data inválida. Use <code>hoje</code>, <code>ontem</code> ou <code>DD/MM/AAAA</code>.")
                return
            dados[campo["chave"]] = d.isoformat()
        elif tp == "ordenhas":
            nums = []
            for p in val.replace(",", ".").split():
                try:
                    nums.append(float(p))
                except ValueError:
                    pass
            if not nums:
                _enviar(chat_id, "Informe as pesagens em kg (ex.: <code>20 18 15</code>).")
                return
            dados[campo["chave"]] = nums
        else:
            dados[campo["chave"]] = val

    sess.dados = json.dumps(dados)
    sess.etapa += 1
    sess.atualizado_em = datetime.utcnow()
    session.add(sess)
    session.commit()
    session.refresh(sess)
    _perguntar_campo(session, sess)


def _finalizar(session: Session, sess: TelegramSessao) -> None:
    chat_id = sess.chat_id
    tipo = sess.fluxo
    dados = json.loads(sess.dados)
    nome = dados.pop("_nome", None)
    dados.pop("_ops", None)
    faltando = [c["chave"] for c in fx.FLUXOS[tipo]["campos"] if c["obrigatorio"] and c["chave"] not in dados]
    if faltando:
        session.delete(sess)
        session.commit()
        _enviar(chat_id, "Faltou responder algo — recomece com /lancar.")
        return
    resumo = fx.montar_resumo(tipo, dados)
    pend = LancamentoPendente(
        tipo=tipo, payload=json.dumps(dados), resumo=resumo,
        solicitante_chat_id=chat_id, solicitante_nome=nome, status="pendente",
    )
    session.add(pend)
    session.delete(sess)
    session.commit()
    _enviar(chat_id, (
        "✅ Enviei para <b>aprovação</b>:\n"
        f"{resumo}\n\n"
        "A conta principal vai aprovar no site ou no app. Obrigado! 🐄"
    ))


def _tratar_callback(session: Session, cq: dict) -> None:
    callback_id = cq["id"]
    chat_id = cq["message"]["chat"]["id"]
    nome = (cq.get("from") or {}).get("first_name")
    data = cq.get("data") or ""
    partes = data.split(":")
    acao = partes[0] if partes else ""

    _responder_callback(callback_id)
    if not _autorizado(chat_id):
        _enviar(chat_id, "🚫 Chat não liberado.")
        return

    # Fluxo operacional (menu, respostas de botão, cancelar).
    if acao == "flow":
        _iniciar_fluxo(session, chat_id, partes[1] if len(partes) > 1 else "", nome)
        return
    if acao == "flowcancel":
        _cancelar_sessao(session, chat_id)
        _enviar(chat_id, "✖️ Ok, cancelei o lançamento.")
        return
    if acao == "ans":
        idx = int(partes[1]) if len(partes) > 1 and partes[1].lstrip("-").isdigit() else None
        sess = _sessao(session, chat_id)
        if sess and sess.fluxo:
            _responder_campo(session, sess, idx=idx)
        return

    # Fluxo financeiro (documento).
    pid = int(partes[1]) if len(partes) > 1 and partes[1].isdigit() else None
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
            # Limpa a fila de updates presos ao reiniciar (evita que uma mensagem
            # que deu erro no passado fique reenviando e travando as novas).
            "drop_pending_updates": True,
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
