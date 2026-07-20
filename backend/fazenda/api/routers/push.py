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
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pywebpush import WebPushException, webpush
from sqlmodel import Session, select

from fazenda.auth import EMAIL_DONO, get_current_user
from fazenda.database import engine, get_session
from fazenda.models import PushNotificacaoEnviada, PushSubscription, Usuario

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


# ---------------------------------------------------------------------------
# Envio de verdade (pywebpush) — usado tanto pelo endpoint de notificações
# (rewire em notificacoes.py) quanto por uma varredura periódica (ver
# despachar_push_pendentes), para o caso de ninguém estar com o app aberto.
# ---------------------------------------------------------------------------
def enviar_push(usuario_id: int, titulo: str, corpo: str, url: str, session: Session | None = None) -> None:
    """Manda uma notificação push real para TODAS as subscriptions ativas do
    usuário. Nunca propaga exceção para quem chamou: uma subscription
    expirada/revogada (404/410 do serviço de push do navegador) é removida
    silenciosamente; qualquer outro erro só vai para o log — um push que
    falha não pode derrubar o fluxo que decidiu o alerta."""
    _session_propria = session is None
    if _session_propria:
        session = Session(engine)
    try:
        subs = session.exec(select(PushSubscription).where(PushSubscription.usuario_id == usuario_id)).all()
        if not subs:
            return
        payload = json.dumps({"title": titulo, "body": corpo, "url": url})
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
    finally:
        if _session_propria:
            session.close()


# ---------------------------------------------------------------------------
# Deduplicação: mesma decisão de alerta (calcular_agenda/notificacoes) pode
# ser recalculada várias vezes por dia (poll do sino a cada 5 min, ou a
# varredura periódica abaixo) — sem isso, o mesmo aviso reenviaria push a
# cada checagem. A chave é derivada do conteúdo do item (tipo+categoria+
# descrição), não de um id próprio, porque nem todo item hoje carrega um id
# estável (ex.: itens de portal têm id; eventos de agenda nem sempre).
# ---------------------------------------------------------------------------
def _chave_item(item: dict) -> str:
    base = f"{item.get('tipo', '')}|{item.get('categoria', '')}|{item.get('descricao', '')}"
    return hashlib.sha256(base.encode()).hexdigest()


# Mesma lógica de destino usada pelo sino no frontend
# (frontend/components/NotificationBell.tsx:destino) — mantém os dois lados
# sincronizados quanto a "clicar neste alerta leva a qual página".
def url_destino(item: dict) -> str:
    chave = f"{item.get('categoria') or ''} {item.get('tipo') or ''}".lower()
    if "aprova" in chave:
        return "/aprovacoes"
    if "portal" in chave:
        return "/portal"
    if "financ" in chave:
        return "/financeiro"
    if "estoque" in chave:
        return "/estoque"
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


def notificar_push_para_itens(usuario_id: int, itens: list[dict], session: Session) -> None:
    """Ponto único chamado pelo rewire (notificacoes.py) e pela varredura
    periódica: para cada item já decidido como alerta hoje, dispara push
    (deduplicado) SE o usuário tiver ao menos uma subscription ativa —
    consulta rápida (sem pywebpush) evita gastar uma chamada de rede à toa.
    O título é fixo por categoria de push (Pendências/Comunicados), não mais
    o `categoria` do item individual — ver _categoria_push."""
    tem_subscription = session.exec(
        select(PushSubscription.id).where(PushSubscription.usuario_id == usuario_id)
    ).first()
    if not tem_subscription:
        return

    hoje = date.today()
    for item in itens:
        chave = _chave_item(item)
        ja_enviado = session.exec(
            select(PushNotificacaoEnviada).where(
                PushNotificacaoEnviada.usuario_id == usuario_id,
                PushNotificacaoEnviada.chave == chave,
                PushNotificacaoEnviada.data_referencia == hoje,
            )
        ).first()
        if ja_enviado:
            continue
        enviar_push(
            usuario_id=usuario_id,
            titulo=TITULOS_PUSH[_categoria_push(item)],
            corpo=item.get("descricao") or "",
            url=url_destino(item),
            session=session,
        )
        session.add(PushNotificacaoEnviada(usuario_id=usuario_id, chave=chave, data_referencia=hoje))
        session.commit()


# Chave fixa (não é hash de conteúdo, ao contrário de _chave_item): o
# resumo é 1x por usuário por dia por definição, então não há "conteúdo"
# variável a deduplicar — a mera existência de uma linha com esta chave e a
# data de hoje já basta para saber que o resumo de hoje já foi enviado.
_CHAVE_AGENDA_DO_DIA = "agenda_do_dia"


def despachar_agenda_do_dia(session: Session) -> None:
    """Varredura diária (mesmo loop de despachar_push_pendentes; a dedup por
    usuário+dia abaixo evita reenviar a cada checagem): manda, para cada
    usuário ativo com subscription, UM push-resumo ("Agenda do dia") com a
    contagem de itens da Agenda que caem em hoje — não um push por item.
    Reaproveita calcular_agenda (fazenda/api/routers/agenda.py, que por sua
    vez usa fazenda.rules.agenda_engine.AgendaEngine.calcular — mesmíssima
    função que monta a Agenda em si e alimenta montar_itens_notificacoes) só
    para CONTAR os itens de hoje; não recalcula nenhuma regra da agenda."""
    from fazenda.api.routers.agenda import calcular_agenda

    hoje = date.today()
    usuarios_com_subscription = session.exec(
        select(Usuario.id).join(PushSubscription, PushSubscription.usuario_id == Usuario.id).where(Usuario.ativo == True)  # noqa: E712
    ).all()
    for usuario_id in set(usuarios_com_subscription):
        usuario = session.get(Usuario, usuario_id)
        if not usuario or not usuario.ativo:
            continue
        ja_enviado = session.exec(
            select(PushNotificacaoEnviada).where(
                PushNotificacaoEnviada.usuario_id == usuario_id,
                PushNotificacaoEnviada.chave == _CHAVE_AGENDA_DO_DIA,
                PushNotificacaoEnviada.data_referencia == hoje,
            )
        ).first()
        if ja_enviado:
            continue
        try:
            agenda = calcular_agenda(data=hoje, dias=0, session=session, usuario=usuario)
            total = sum(1 for e in agenda["eventos"] if e["data"] == hoje.isoformat())
        except Exception:
            logger.exception("Falha ao calcular agenda do dia para usuário %s", usuario_id)
            continue
        if total == 0:
            continue  # sem itens hoje: não manda push vazio (e não marca como enviado — se
            # algum item surgir mais tarde no mesmo dia, a próxima checagem ainda pode avisar)
        enviar_push(
            usuario_id=usuario_id,
            titulo="Agenda do dia",
            corpo=f"Você tem {total} atividade{'s' if total != 1 else ''} na agenda hoje",
            url="/agenda",
            session=session,
        )
        session.add(PushNotificacaoEnviada(usuario_id=usuario_id, chave=_CHAVE_AGENDA_DO_DIA, data_referencia=hoje))
        session.commit()


def despachar_push_pendentes(session: Session) -> None:
    """Varredura periódica (ver loop em main.py) — cobre o caso de NINGUÉM
    estar com o app aberto: sem isso, o rewire em notificacoes.py só dispara
    quando alguém efetivamente consulta o sino (poll do app aberto), o que
    não cumpre "funciona mesmo com o app fechado". Reaproveita 100% da mesma
    função que decide os alertas (montar_itens_notificacoes) — só itera cada
    usuário ativo com subscription e despacha o que for novo."""
    from fazenda.api.routers.notificacoes import montar_itens_notificacoes

    usuarios_com_subscription = session.exec(
        select(Usuario.id).join(PushSubscription, PushSubscription.usuario_id == Usuario.id).where(Usuario.ativo == True)  # noqa: E712
    ).all()
    for usuario_id in set(usuarios_com_subscription):
        usuario = session.get(Usuario, usuario_id)
        if not usuario or not usuario.ativo:
            continue
        try:
            itens = montar_itens_notificacoes(usuario, session)
            notificar_push_para_itens(usuario_id, itens, session)
        except Exception:
            logger.exception("Falha ao despachar push periódico para usuário %s", usuario_id)
