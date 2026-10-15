"""
Router de push (Web Push API) — canal de entrega ADICIONAL para os MESMOS
alertas que já alimentam o sininho (ver fazenda/api/routers/notificacoes.py):
contas vencendo, estoque abaixo do mínimo, pendências de agenda, mensagens
do Portal e exclusões pendentes. Este módulo não decide "quando avisar" —
isso continua inteiramente em fazenda.rules.agenda_engine.calcular() e em
notificacoes.montar_itens_notificacoes(); aqui só entregamos a MESMA decisão
via notificação nativa do navegador, inclusive com o app fechado.

Chaves VAPID (identificam o servidor perante o serviço de push do
navegador): variáveis de ambiente VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY /
VAPID_SUBJECT — mesmo padrão de AUTH_SECRET em fazenda/auth.py. PRODUÇÃO
DEVE definir as duas primeiras (ex.: `vapid --gen` do próprio py_vapid, ou
`web-push generate-vapid-keys` do pacote Node) — sem elas, cada restart do
processo gera um par novo (ver _gerar_par_dev abaixo) e todas as
subscriptions antigas passam a falhar (404/410), exigindo reinscrição.
Nunca hardcode uma chave real aqui: chave privada em texto no repositório
fica exposta a qualquer um com acesso de leitura ao código.
VAPID_PUBLIC_KEY é o valor exposto ao frontend (GET /push/chave-publica,
sem exigir login) para `pushManager.subscribe({ applicationServerKey: ... })`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pywebpush import WebPushException, webpush
from sqlmodel import Session, select

from fazenda.auth import EMAIL_DONO, get_current_user
from fazenda.database import engine, get_session
from fazenda.models import Pessoa, PushAck, PushEnvio, PushNotificacaoEnviada, PushSubscription, PushTokenFcm, Usuario
from fazenda.rules import fcm
from fazenda.rules.datas import agora_local, hoje_local

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["push"])


def _gerar_par_dev() -> tuple[str, str]:
    """Só roda quando VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY não estão definidas
    (dev local, out-of-the-box) — gera um par EFÊMERO a cada start do
    processo, nunca escrito no código-fonte. Formato: ponto público
    descomprimido (X9.62) e escalar privado bruto (32 bytes), ambos
    base64url sem padding — o mesmo formato aceito por pywebpush/py_vapid
    e por `pushManager.subscribe({ applicationServerKey })` no navegador."""
    from py_vapid import Vapid02
    from cryptography.hazmat.primitives import serialization

    vapid = Vapid02()
    vapid.generate_keys()
    pub_raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
    )
    priv_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
    return b64(pub_raw), b64(priv_raw)


VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
    logger.warning(
        "VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY não definidas — usando par efêmero "
        "de desenvolvimento (gerado agora, só nesta execução). Defina as duas "
        "variáveis em produção, ou toda subscription feita antes do próximo "
        "restart do servidor para de funcionar."
    )
    VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY = _gerar_par_dev()
# "sub" do JWT do VAPID precisa ser um mailto: ou URL — reaproveita o e-mail
# do proprietário (fazenda.auth.EMAIL_DONO) como contato padrão.
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", f"mailto:{EMAIL_DONO}")


@router.get("/chave-publica")
def chave_publica() -> dict:
    """Público (sem login) — o frontend precisa disto antes mesmo de o
    usuário terminar de se inscrever, para montar `applicationServerKey`."""
    return {"chave_publica": VAPID_PUBLIC_KEY}


# ---------------------------------------------------------------------------
# BUG DE SEGURANÇA CORRIGIDO (CWE-918, SSRF): `endpoint` chegava como texto
# livre do cliente, era gravado sem checagem alguma (só "não vazio") e depois
# ia direto para `webpush(subscription_info={"endpoint": sub.endpoint, ...})`
# (ver _enviar_web_push abaixo) — o pywebpush instalado faz
# `self.mod_or_session.post(endpoint, ...)` sem validar esquema/host. Como o
# disparo (notificar_push_para_itens) roda dentro do próprio GET
# /notificacoes/ do usuário logado, QUALQUER usuário autenticado (o papel
# mais baixo do SaaS) conseguia transformar o backend em proxy para
# 169.254.169.254 (metadata da cloud), 127.0.0.1 e a rede interna do Railway
# (ex.: o próprio Postgres) — bastava cadastrar esse "endpoint" malicioso.
#
# A correção NÃO tenta validar o texto da URL (checar esquema/IP no momento
# do cadastro não protege contra um host público cujo DNS resolve depois
# para um endereço interno — "DNS rebinding" — nem contra um redirect que só
# aparece na hora do POST de verdade, depois de qualquer validação). Em vez
# disso, restringimos a um allowlist FECHADO dos hosts que os fabricantes de
# navegador usam para entregar Web Push — é um conjunto pequeno e conhecido
# (Chrome/Edge/Android via FCM, Firefox via Mozilla, Safari via Apple, Edge
# legado/Windows via WNS): nenhum deles está sob controle do atacante, então
# não importa se o DNS "rebindar" ou se a resposta redirecionar — a URL
# cadastrada já não teria passado na checagem de host.
#
# O QUE ISTO NÃO COBRE: se um destes 4 provedores um dia for comprometido ou
# passar a redirecionar internamente para algo malicioso, o allowlist não
# pegaria — mas isso está fora do modelo de ameaça de "usuário autenticado
# comum do SaaS" que este achado cobre.
# ---------------------------------------------------------------------------
_PUSH_HOSTS_EXATOS = {
    "fcm.googleapis.com",                  # Chrome, Edge (Chromium), navegadores Android
    "updates.push.services.mozilla.com",   # Firefox
    "web.push.apple.com",                  # Safari (macOS/iOS)
    "notify.windows.com",                  # Edge legado / WNS
}
_PUSH_HOSTS_SUFIXOS = (
    ".notify.windows.com",  # WNS usa subdomínios regionais, ex.: wns2-par3p.notify.windows.com
)


def _endpoint_de_push_valido(endpoint: str) -> bool:
    """True só se `endpoint` apontar para um dos serviços de entrega de Web
    Push conhecidos (ver comentário acima). Exige HTTPS (Web Push nunca usa
    outro esquema em produção) e compara o HOST — nunca faz `requests`/DNS
    aqui, de propósito: qualquer resolução feita agora poderia divergir da
    resolução feita depois, na hora real do POST (TOCTOU)."""
    try:
        partes = urlparse(endpoint)
    except ValueError:
        return False
    if partes.scheme != "https":
        return False
    host = (partes.hostname or "").lower()
    if not host:
        return False
    if host in _PUSH_HOSTS_EXATOS:
        return True
    return any(host.endswith(sufixo) for sufixo in _PUSH_HOSTS_SUFIXOS)


class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: dict
    user_agent: str | None = None


@router.post("/subscribe")
def subscribe(
    dados: PushSubscriptionIn,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Salva (ou atualiza, se o endpoint já existir para este usuário) a
    subscription de push do navegador do usuário logado."""
    p256dh = (dados.keys or {}).get("p256dh")
    auth = (dados.keys or {}).get("auth")
    if not dados.endpoint or not p256dh or not auth:
        raise HTTPException(status_code=422, detail="Subscription incompleta (endpoint/p256dh/auth)")
    # Ver bloco de comentário de _endpoint_de_push_valido acima: fecha o SSRF
    # (CWE-918) recusando qualquer endpoint que não seja um serviço de
    # entrega de Web Push conhecido, ANTES de gravar no banco — é o único
    # lugar por onde este campo entra no sistema.
    if not _endpoint_de_push_valido(dados.endpoint):
        raise HTTPException(
            status_code=422,
            detail="Endpoint de push não reconhecido — só são aceitos os serviços de entrega dos navegadores suportados",
        )

    existente = session.exec(
        select(PushSubscription).where(
            PushSubscription.usuario_id == user.id,
            PushSubscription.endpoint == dados.endpoint,
        )
    ).first()
    if existente:
        existente.p256dh = p256dh
        existente.auth = auth
        existente.user_agent = dados.user_agent
        session.add(existente)
    else:
        session.add(PushSubscription(
            usuario_id=user.id, endpoint=dados.endpoint, p256dh=p256dh, auth=auth,
            user_agent=dados.user_agent,
        ))
    session.commit()
    return {"ok": True}


class PushUnsubscribeIn(BaseModel):
    # None = remove todas as subscriptions do usuário (ex.: "desativar em
    # todos os dispositivos"); com endpoint, remove só a deste navegador.
    endpoint: str | None = None


@router.delete("/subscribe")
def unsubscribe(
    dados: PushUnsubscribeIn | None = None,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    query = select(PushSubscription).where(PushSubscription.usuario_id == user.id)
    if dados and dados.endpoint:
        query = query.where(PushSubscription.endpoint == dados.endpoint)
    subs = session.exec(query).all()
    for s in subs:
        session.delete(s)
    session.commit()
    return {"ok": True, "removidas": len(subs)}


class PushTokenFcmIn(BaseModel):
    token: str
    plataforma: str = "android"
    modelo: str | None = None
    device_id: str | None = None


@router.post("/registrar-fcm")
def registrar_fcm(
    dados: PushTokenFcmIn,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Registra (ou reaproveita) o token FCM do app Android nativo deste
    usuário — canal irmão de /subscribe (Web Push), usado pelo app Capacitor
    (Web Push não é confiável na WebView com o app fechado). Idempotente: o
    app chama isto toda vez que abre, já que o token pode rotacionar sozinho.
    Se o token já existir para OUTRO usuário (mesmo aparelho, outra pessoa
    logou depois), a linha troca de dono em vez de duplicar — senão o
    funcionário anterior continuaria recebendo push no aparelho que não é
    mais dele."""
    if not dados.token:
        raise HTTPException(status_code=422, detail="Token FCM vazio")

    existente = session.exec(select(PushTokenFcm).where(PushTokenFcm.token == dados.token)).first()
    if existente:
        existente.usuario_id = user.id
        existente.plataforma = dados.plataforma
        existente.modelo = dados.modelo
        existente.device_id = dados.device_id
        existente.atualizado_em = datetime.utcnow()
        session.add(existente)
    else:
        session.add(PushTokenFcm(
            usuario_id=user.id, token=dados.token, plataforma=dados.plataforma,
            modelo=dados.modelo, device_id=dados.device_id,
        ))
    session.commit()
    return {"ok": True}


class PushTokenFcmOutIn(BaseModel):
    token: str | None = None


@router.delete("/registrar-fcm")
def remover_fcm(
    dados: PushTokenFcmOutIn | None = None,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Espelho de DELETE /push/subscribe: sem token, remove todos os tokens
    FCM do usuário; com token, só o daquele aparelho. Chamado no logout do
    app nativo — sem isso, o aparelho continuaria recebendo push do usuário
    que acabou de sair."""
    query = select(PushTokenFcm).where(PushTokenFcm.usuario_id == user.id)
    if dados and dados.token:
        query = query.where(PushTokenFcm.token == dados.token)
    tokens = session.exec(query).all()
    for t in tokens:
        session.delete(t)
    session.commit()
    return {"ok": True, "removidos": len(tokens)}


# ---------------------------------------------------------------------------
# Envio de verdade — dois canais (Web Push do navegador/PWA via pywebpush, e
# FCM do app Android nativo via fazenda/rules/fcm.py). enviar_push() é a
# fachada única usada tanto pelo endpoint de notificações (rewire em
# notificacoes.py) quanto pela varredura periódica (ver
# despachar_push_pendentes), para o caso de ninguém estar com o app aberto —
# manda para TODOS os canais que o usuário tiver, sem duplicar (são
# aparelhos/instalações distintas; a dedup de "já mandei esse alerta hoje" é
# por usuário, acima do canal — ver PushNotificacaoEnviada).
# ---------------------------------------------------------------------------
def _enviar_web_push(usuario_id: int, titulo: str, corpo: str, url: str, session: Session, count: int | None) -> None:
    subs = session.exec(select(PushSubscription).where(PushSubscription.usuario_id == usuario_id)).all()
    if not subs:
        return
    dados_payload = {"title": titulo, "body": corpo, "url": url}
    if count is not None:
        dados_payload["count"] = count
    payload = json.dumps(dados_payload)
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                session.delete(sub)
                session.commit()
            else:
                logger.warning("Falha ao enviar push (usuário %s): %s", usuario_id, e)
        except Exception:  # nunca deixa o canal de push derrubar o chamador
            logger.exception("Erro inesperado ao enviar push (usuário %s)", usuario_id)


def _enviar_fcm(usuario_id: int, titulo: str, corpo: str, url: str, session: Session, count: int | None, categoria: str | None = None) -> None:
    if not fcm.habilitado():
        return
    tokens = session.exec(select(PushTokenFcm).where(PushTokenFcm.usuario_id == usuario_id)).all()
    for t in tokens:
        try:
            fcm.enviar(
                token=t.token,
                titulo=titulo,
                corpo=corpo,
                url=url,
                count=count,
                session=session,
                usuario_id=usuario_id,
                push_token_id=t.id,
                categoria=categoria or "pendencia",
                icon="ic_notification_cowdata",
                channel_id="cowdata_notificacoes",
            )
        except fcm.FcmTokenInvalido:
            session.delete(t)
            session.commit()
        except Exception:  # nunca deixa o canal de push derrubar o chamador
            logger.exception("Erro inesperado ao enviar push via FCM (usuário %s)", usuario_id)


def enviar_push(
    usuario_id: int, titulo: str, corpo: str, url: str, session: Session | None = None, count: int | None = None,
    categoria: str | None = None,
) -> None:
    """Manda uma notificação push real para TODOS os canais ativos do
    usuário (Web Push do navegador/PWA + FCM do app Android nativo). Nunca
    propaga exceção para quem chamou: uma subscription/token expirado é
    removido silenciosamente; qualquer outro erro só vai para o log — um
    push que falha não pode derrubar o fluxo que decidiu o alerta.

    `count`, quando informado, viaja no payload e é usado pelo service worker
    (sw.js)/pelo ícone do app nativo para atualizar o "badge" mesmo com o app
    fechado — hoje só a Agenda do dia informa esse número (ver
    despachar_resumo_da_noite abaixo).
    
    `categoria`: categoria do push ("pendencia" | "comunicado") para auditoria no push_envio."""
    _session_propria = session is None
    if _session_propria:
        session = Session(engine)
    try:
        _enviar_web_push(usuario_id, titulo, corpo, url, session, count)
        _enviar_fcm(usuario_id, titulo, corpo, url, session, count, categoria)
    finally:
        if _session_propria:
            session.close()


def tem_canal_push(usuario_id: int, session: Session) -> bool:
    """True se o usuário tem AO MENOS UM canal de push ativo (Web Push ou
    FCM) — usado para não gastar uma consulta/chamada de rede à toa quando
    não há para onde entregar."""
    if session.exec(select(PushSubscription.id).where(PushSubscription.usuario_id == usuario_id)).first():
        return True
    return session.exec(select(PushTokenFcm.id).where(PushTokenFcm.usuario_id == usuario_id)).first() is not None


def usuarios_com_canal_push(session: Session) -> set[int]:
    """União dos usuários com Web Push OU FCM — substitui os antigos
    `select(Usuario.id).join(PushSubscription, ...)`. Sem isso, quem só tem
    o app nativo (nunca clicou em "ativar notificações" no navegador) nunca
    entraria nas varreduras periódicas abaixo."""
    web = session.exec(select(PushSubscription.usuario_id)).all()
    nativo = session.exec(select(PushTokenFcm.usuario_id)).all()
    return set(web) | set(nativo)


# ---------------------------------------------------------------------------
# Quando avisar (regra do dono, 15/10/2026): o app NÃO fica repetindo.
#   1. À NOITE (a partir de HORA_RESUMO_NOITE, horário de Brasília) UM resumo com
#      todos os compromissos do dia seguinte (despachar_resumo_da_noite).
#   2. Depois disso, só o que for NOVO — e UMA vez por evento. O que já entrou no
#      resumo da noite, ou já foi avisado, não avisa de novo.
#
# Como se garante "uma vez por evento": a identidade do evento (_chave_evento) NÃO
# leva a data de hoje. Antes a chave era (conteúdo + dia), então todo alerta que a
# Agenda recria diariamente (atrasadas, estoque abaixo do mínimo, descarte vencido,
# conta vencida...) voltava a avisar todo dia, e cada item virava um push próprio.
# Agora a marca fica enquanto o evento continua existindo, e é esquecida (reaberta)
# quando ele some da lista da varredura — assim, se o mesmo problema voltar depois
# de resolvido, é de fato um evento novo e avisa uma vez.
# ---------------------------------------------------------------------------
HORA_RESUMO_NOITE = 18          # a partir daqui (Brasília) sai o resumo de amanhã
LIMITE_PUSH_INDIVIDUAL = 3      # mais novidades que isto numa varredura viram UM push agrupado
_PREFIXO_CHAVE = "e:"           # marcas no formato novo (as antigas eram o hash puro)
_CHAVE_RESUMO_NOITE = "resumo_amanha"   # 1 por usuário por dia-alvo (data_referencia = o dia dos compromissos)


def _hash(base: str) -> str:
    return hashlib.sha256(base.encode()).hexdigest()


def _chave_item(item: dict) -> str:
    """Chave ANTIGA (conteúdo, sem identidade do evento). Só para reconhecer marcas gravadas antes da
    mudança e não reavisar tudo no deploy."""
    return _hash(f"{item.get('tipo', '')}|{item.get('categoria', '')}|{item.get('descricao', '')}")


def _chave_evento(item: dict) -> str:
    """Identidade estável do evento: nada que mude de um dia para o outro."""
    if item.get("portal_mensagem_id") is not None:
        base = f"portal|{item['portal_mensagem_id']}"
    elif item.get("solicitacao_id") is not None:
        base = f"exclusao|{item['solicitacao_id']}"
    elif item.get("alerta_id") is not None:
        base = f"alerta_indicador|{item['alerta_id']}"
    elif item.get("evento_tipo") == "visita_reprodutiva":
        # a descrição muda ("Amanhã: …" na véspera, "Visita reprodutiva" no dia): a visita é UM evento
        base = f"visita_reprodutiva|{item.get('data_visita') or ''}"
    else:
        base = "|".join(str(item.get(k) or "") for k in ("tipo", "evento_tipo", "categoria", "descricao", "numero_animal", "ref"))
    return _PREFIXO_CHAVE + _hash(base)


def _data_efetiva(item: dict) -> date | None:
    """Dia a que o item se refere (a visita reprodutiva avisa na véspera: vale a data da visita)."""
    bruto = item.get("data_visita") or item.get("data")
    try:
        return date.fromisoformat(str(bruto)[:10]) if bruto else None
    except ValueError:
        return None


def _ja_avisado(session: Session, usuario_id: int, item: dict, chave: str, hoje: date) -> bool:
    if session.exec(select(PushNotificacaoEnviada.id).where(
        PushNotificacaoEnviada.usuario_id == usuario_id, PushNotificacaoEnviada.chave == chave,
    )).first() is not None:
        return True
    # Marca no formato antigo (conteúdo + dia): evita um "reaviso geral" no deploy. Itens da agenda só valem
    # se avisados HOJE (a mesma tarefa semanal de outra semana é outro evento); mensagens/pendências/alertas,
    # que não têm data, valem de qualquer dia.
    sem_data = any(item.get(k) is not None for k in ("portal_mensagem_id", "solicitacao_id", "alerta_id"))
    q = select(PushNotificacaoEnviada.id).where(
        PushNotificacaoEnviada.usuario_id == usuario_id, PushNotificacaoEnviada.chave == _chave_item(item),
    )
    if not sem_data:
        q = q.where(PushNotificacaoEnviada.data_referencia == hoje)
    return session.exec(q).first() is not None


def _marcar(session: Session, usuario_id: int, chave: str, hoje: date) -> None:
    session.add(PushNotificacaoEnviada(usuario_id=usuario_id, chave=chave, data_referencia=hoje))
    session.commit()


# Mesma lógica de destino usada pelo sino no frontend
# (frontend/components/NotificationBell.tsx:destino) — mantém os dois lados
# sincronizados quanto a "clicar neste alerta leva a qual página".
def url_destino(item: dict) -> str:
    # Sugestão de mudança de lote só se resolve dentro da janela "Ver
    # sugestão" da própria Agenda — sem o evento_id, o toque na notificação
    # caía na tela genérica da Agenda sem achar o item pra tratar (ver
    # #sugestão-de-lote-presa: usuário via o alerta mas não conseguia agir).
    if item.get("evento_tipo") == "sugestao_movimentacao" and item.get("evento_id"):
        return f"/agenda?abrir_sugestao={quote(str(item['evento_id']))}"
    chave = f"{item.get('categoria') or ''} {item.get('tipo') or ''}".lower()
    if "aprova" in chave:
        return "/aprovacoes"
    if "portal" in chave:
        return "/portal"
    if "financ" in chave:
        return "/financeiro"
    if "estoque" in chave:
        return "/estoque"
    if "indicador" in chave:
        return "/indicadores"
    return "/agenda"


# ---------------------------------------------------------------------------
# Categorização do push: o usuário passou a ver 3 "canais" de push
# (Agenda do dia / Pendências / Comunicados) em vez de um título por item
# (antes era item.get("categoria"), o que fragmentava a notificação em
# dezenas de títulos diferentes). "Comunicado" = item que só informa, sem
# gerar movimentação/ação do usuário (mensagem do Portal, ou aviso
# informativo de agenda tipo "nova dieta" — ver COMUNICADO_PREFIXOS/
# "comunicado" em agenda.py; aqui chega achatado em tipo="agenda", então a
# palavra "dieta" na categoria/descrição é o sinal disponível). Todo o resto
# (exclusão pendente, conta vencendo, estoque baixo, demais eventos de
# agenda) é "pendência" — item acionável.
TITULOS_PUSH = {
    "comunicado": "Comunicados",
    "pendencia": "Pendências",
}


def _categoria_push(item: dict) -> str:
    if (item.get("tipo") or "") == "portal_mensagem":
        return "comunicado"
    texto = f"{item.get('categoria') or ''} {item.get('descricao') or ''}".lower()
    if "dieta" in texto:
        return "comunicado"
    return "pendencia"


def _enviar_novidades(usuario_id: int, novos: list[dict], session: Session) -> None:
    """Entrega o que é novo: um push por item até LIMITE_PUSH_INDIVIDUAL; acima disso, UM push agrupado."""
    if not novos:
        return
    if len(novos) <= LIMITE_PUSH_INDIVIDUAL:
        for item in novos:
            cat = _categoria_push(item)
            enviar_push(
                usuario_id=usuario_id, titulo=TITULOS_PUSH[cat], corpo=item.get("descricao") or "",
                url=url_destino(item), session=session, categoria=cat,
            )
        return
    enviar_push(
        usuario_id=usuario_id, titulo=TITULOS_PUSH["pendencia"],
        corpo=f"{len(novos)} novidades: " + "; ".join(_curto(i.get("descricao")) for i in novos[:3]) + f" e mais {len(novos) - 3}",
        url="/agenda", session=session, categoria="pendencia",
    )


def _curto(texto: str | None, limite: int = 60) -> str:
    texto = (texto or "").strip()
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def notificar_push_para_itens(
    usuario_id: int, itens: list[dict], session: Session, *, incluir_amanha: bool = False, reabrir: bool = False,
) -> None:
    """Ponto único do push de pendências (sino e varredura): avisa só o que é NOVO e UMA vez por evento
    (identidade em _chave_evento, sem a data de hoje). Só se o usuário tiver canal ativo (Web Push ou FCM).

    - Item que se refere a um dia FUTURO (ex.: a visita reprodutiva na véspera) não avisa aqui: é assunto do
      resumo da noite. `incluir_amanha=True` (varredura, depois que o resumo saiu) libera os de amanhã.
    - `reabrir=True` (só a varredura, que enxerga a lista completa): esquece a marca de quem saiu da lista,
      para o mesmo problema, se voltar depois de resolvido, avisar de novo UMA vez.
    - A marca é gravada ANTES do envio: duas consultas ao mesmo tempo (sino aberto em duas telas + varredura)
      não mandam o mesmo aviso duas vezes."""
    if not tem_canal_push(usuario_id, session):
        return

    hoje = hoje_local()
    limite = hoje + timedelta(days=1 if incluir_amanha else 0)
    presentes: set[str] = set()
    novos: list[dict] = []
    for item in itens:
        chave = _chave_evento(item)
        presentes.add(chave)
        efetiva = _data_efetiva(item)
        if efetiva is not None and efetiva > limite:
            continue
        if _ja_avisado(session, usuario_id, item, chave, hoje):
            if session.exec(select(PushNotificacaoEnviada.id).where(
                PushNotificacaoEnviada.usuario_id == usuario_id, PushNotificacaoEnviada.chave == chave,
            )).first() is None:
                _marcar(session, usuario_id, chave, hoje)   # migra a marca antiga para a nova, sem avisar
            continue
        _marcar(session, usuario_id, chave, hoje)
        novos.append(item)

    if reabrir:
        for marca in session.exec(select(PushNotificacaoEnviada).where(
            PushNotificacaoEnviada.usuario_id == usuario_id, PushNotificacaoEnviada.chave.like(_PREFIXO_CHAVE + "%"),
        )).all():
            if marca.chave not in presentes:
                session.delete(marca)
        session.commit()

    _enviar_novidades(usuario_id, novos, session)


def _fazenda_do_usuario(session: Session, usuario: Usuario) -> int | None:
    """Fazenda a que este login pertence (mesmo caminho Usuario.pessoa_id →
    Pessoa.fazenda_id usado em todo o resto do cadastro/RH) — necessário
    aqui porque estas varreduras rodam fora de uma requisição HTTP (sem
    Authorization/token), então não há como Depends(get_fazenda_atual_id)
    resolver nada; sem isto, calcular_agenda/montar_itens_notificacoes
    recebiam fazenda_id não resolvido e misturavam agenda e alertas de TODAS
    as fazendas no push de qualquer usuário (bug real encontrado em produção)."""
    if not usuario.pessoa_id:
        return None
    pessoa = session.get(Pessoa, usuario.pessoa_id)
    return pessoa.fazenda_id if pessoa else None


def _resumo_da_noite_enviado(session: Session, usuario_id: int, alvo: date) -> bool:
    return session.exec(select(PushNotificacaoEnviada.id).where(
        PushNotificacaoEnviada.usuario_id == usuario_id,
        PushNotificacaoEnviada.chave == _CHAVE_RESUMO_NOITE,
        PushNotificacaoEnviada.data_referencia == alvo,
    )).first() is not None


def despachar_resumo_da_noite(session: Session) -> None:
    """À noite (a partir de HORA_RESUMO_NOITE, Brasília): UM push por usuário com TODOS os compromissos do dia
    seguinte (não um por item). Substitui o antigo "Agenda do dia" da manhã, que repetia o que já se sabia.

    Os itens que entram no resumo ficam marcados como avisados: nem hoje à noite nem amanhã de manhã voltam
    como push individual — só um evento NOVO (criado depois) avisa, uma vez. Sem compromissos amanhã, não manda
    push vazio e não marca (se algo surgir mais tarde, a próxima volta ainda manda o resumo)."""
    from fazenda.api.routers.notificacoes import itens_da_agenda

    agora = agora_local()
    if agora.hour < HORA_RESUMO_NOITE:
        return
    alvo = agora.date() + timedelta(days=1)
    for usuario_id in usuarios_com_canal_push(session):
        usuario = session.get(Usuario, usuario_id)
        if not usuario or not usuario.ativo or _resumo_da_noite_enviado(session, usuario_id, alvo):
            continue
        try:
            itens = itens_da_agenda(usuario, session, _fazenda_do_usuario(session, usuario), alvo)
        except Exception:
            logger.exception("Falha ao calcular os compromissos de amanhã para o usuário %s", usuario_id)
            continue
        if not itens:
            continue
        total = len(itens)
        resumo = "; ".join(_curto(i.get("descricao")) for i in itens[:3]) + (f" e mais {total - 3}" if total > 3 else "")
        # grava as marcas ANTES de enviar (mesma razão de notificar_push_para_itens)
        for item in itens:
            chave = _chave_evento(item)
            if session.exec(select(PushNotificacaoEnviada.id).where(
                PushNotificacaoEnviada.usuario_id == usuario_id, PushNotificacaoEnviada.chave == chave,
            )).first() is None:
                session.add(PushNotificacaoEnviada(usuario_id=usuario_id, chave=chave, data_referencia=agora.date()))
        session.add(PushNotificacaoEnviada(usuario_id=usuario_id, chave=_CHAVE_RESUMO_NOITE, data_referencia=alvo))
        session.commit()
        enviar_push(
            usuario_id=usuario_id,
            titulo="Compromissos de amanhã",
            corpo=f"Amanhã: {total} compromisso{'s' if total != 1 else ''} — {resumo}",
            url="/agenda", session=session, categoria="comunicado",
        )


def _limpar_marcas_velhas(session: Session, hoje: date) -> None:
    """Marcas do formato antigo (conteúdo + dia), do "Agenda do dia" e dos resumos já vencidos não servem mais."""
    for marca in session.exec(select(PushNotificacaoEnviada).where(
        PushNotificacaoEnviada.data_referencia < hoje - timedelta(days=7),
    )).all():
        if not marca.chave.startswith(_PREFIXO_CHAVE):
            session.delete(marca)
    session.commit()


def despachar_push_pendentes(session: Session) -> None:
    """Varredura periódica (loop de main.py; cobre o app fechado): avisa só o que é NOVO, uma vez por evento.
    Depois que o resumo da noite saiu, também enxerga o que for criado para amanhã. Reaproveita a mesma
    função que decide os alertas do sino (montar_itens_notificacoes)."""
    from fazenda.api.routers.notificacoes import itens_da_agenda, montar_itens_notificacoes

    agora = agora_local()
    hoje = agora.date()
    alvo = hoje + timedelta(days=1)
    try:
        _limpar_marcas_velhas(session, hoje)
    except Exception:
        logger.exception("Falha ao limpar marcas antigas de push")
    for usuario_id in usuarios_com_canal_push(session):
        usuario = session.get(Usuario, usuario_id)
        if not usuario or not usuario.ativo:
            continue
        try:
            fazenda_id = _fazenda_do_usuario(session, usuario)
            itens = montar_itens_notificacoes(usuario, session, fazenda_id)
            depois_do_resumo = agora.hour >= HORA_RESUMO_NOITE and _resumo_da_noite_enviado(session, usuario_id, alvo)
            if depois_do_resumo:
                itens = itens + itens_da_agenda(usuario, session, fazenda_id, alvo)
            notificar_push_para_itens(usuario_id, itens, session, incluir_amanha=depois_do_resumo, reabrir=True)
        except Exception:
            logger.exception("Falha ao despachar push periódico para usuário %s", usuario_id)


# ---------------------------------------------------------------------------
# /push/ack — confirmação de recebimento (app Android nativo)
# O app (Java/Kotlin FirebaseMessagingService) chama isto ao receber a
# notificação FCM, para registrar o ack no push_ack. Permite auditoria:
# "o backend mandou (push_envio) E o celular recebeu (push_ack)?"
# ---------------------------------------------------------------------------
class PushAckIn(BaseModel):
    fcm_message_id: str | None = None  # opcional: id da mensagem FCM (name=projects/.../messages/{id})
    push_envio_id: int | None = None   # opcional: id do push_envio se o app souber
    token_fcm: str | None = None       # token que recebeu (para diagnóstico)
    estado_app: str                    # "primeiro_plano" | "segundo_plano" | "tocada"


@router.post("/ack")
def registrar_ack(
    dados: PushAckIn,
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Registra o ack de recebimento de push FCM no push_ack.
    Se push_envio_id não vier, tenta achar pelo fcm_message_id mais recente do usuário."""
    push_envio_id = dados.push_envio_id
    if push_envio_id is None and dados.fcm_message_id:
        envio = session.exec(
            select(PushEnvio).where(
                PushEnvio.usuario_id == user.id,
                PushEnvio.fcm_message_id == dados.fcm_message_id,
            )
        ).first()
        if envio:
            push_envio_id = envio.id
    if push_envio_id is None:
        # Fallback: o mais recente do usuário que ainda não tem ack
        envio = session.exec(
            select(PushEnvio).where(
                PushEnvio.usuario_id == user.id,
                PushEnvio.resultado == "ok",
            ).order_by(PushEnvio.enviado_em.desc())
        ).first()
        if envio:
            push_envio_id = envio.id
    if push_envio_id is None:
        raise HTTPException(status_code=404, detail="Nenhum envio correspondente encontrado para este usuário")
    
    # Verifica se já existe ack para este envio (idempotente)
    ack_existente = session.exec(
        select(PushAck).where(
            PushAck.push_envio_id == push_envio_id,
            PushAck.usuario_id == user.id,
        )
    ).first()
    if ack_existente:
        return {"ok": True, "ack_id": ack_existente.id, "ja_existia": True}
    
    ack = PushAck(
        push_envio_id=push_envio_id,
        usuario_id=user.id,
        token_fcm=dados.token_fcm,
        estado_app=dados.estado_app,
        recebido_em=datetime.utcnow(),
    )
    session.add(ack)
    session.commit()
    session.refresh(ack)
    return {"ok": True, "ack_id": ack.id, "ja_existia": False}
