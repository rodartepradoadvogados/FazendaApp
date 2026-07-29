"""
Cliente do Firebase Cloud Messaging (HTTP v1) — canal de push do APP ANDROID
NATIVO (Capacitor). Complementa, não substitui, o Web Push do navegador/PWA
(pywebpush, ver fazenda/api/routers/push.py): dentro da WebView do Capacitor
não existe processo de navegador em segundo plano, então PushManager/service
worker não entregam com o app fechado — o FCM entrega.

REST puro via httpx (mesmo estilo de fazenda/rules/asaas.py e
supabase_storage.py). A única dependência nova é `google-auth`, e SÓ para
gerar o access token OAuth2 da conta de serviço — o SDK firebase-admin
inteiro (grpc, firestore, storage...) seria desproporcional para uma única
chamada REST.

Documentação: https://firebase.google.com/docs/cloud-messaging/send-message
  POST https://fcm.googleapis.com/v1/projects/{project_id}/messages:send

Sem FCM_SERVICE_ACCOUNT_JSON configurado, habilitado() é False e enviar()
nunca é chamado pelo lado do chamador (fazenda/api/routers/push.py já checa
antes) — mas mesmo se chamado, levanta RuntimeError com mensagem clara em
vez de falhar silenciosamente.
"""
from __future__ import annotations

import base64
import json

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from fazenda.config import settings

_ESCOPO = "https://www.googleapis.com/auth/firebase.messaging"
_TIMEOUT = 15  # segundos

_credenciais_cache: service_account.Credentials | None = None


def habilitado() -> bool:
    return bool(settings.fcm_service_account_json)


def _carregar_json_conta_servico() -> dict:
    bruto = settings.fcm_service_account_json
    # Tolerância a colar em base64 (mais robusto que exigir JSON cru numa
    # variável de ambiente multi-linha) — tenta JSON direto primeiro.
    try:
        dados = json.loads(bruto)
    except (json.JSONDecodeError, TypeError):
        try:
            dados = json.loads(base64.b64decode(bruto))
        except Exception as exc:
            raise RuntimeError(
                "FCM_SERVICE_ACCOUNT_JSON inválido — deve ser o JSON da conta de "
                "serviço (Firebase Console > Configurações do projeto > Contas de "
                "serviço > Gerar nova chave privada), colado inteiro ou em base64."
            ) from exc
    # Alguns painéis (ex.: colar numa env var de linha única) escapam as
    # quebras de linha da private_key literalmente como "\n" — desescapa se
    # ainda estiver assim, senão google-auth falha ao desserializar a chave.
    chave = dados.get("private_key", "")
    if "\\n" in chave and "\n" not in chave:
        dados["private_key"] = chave.replace("\\n", "\n")
    return dados


def _credenciais() -> service_account.Credentials:
    global _credenciais_cache
    if not habilitado():
        raise RuntimeError(
            "Push nativo (FCM) não configurado — defina FCM_SERVICE_ACCOUNT_JSON "
            "nas variáveis de ambiente (Firebase Console > Configurações do "
            "projeto > Contas de serviço > Gerar nova chave privada)."
        )
    if _credenciais_cache is None:
        dados = _carregar_json_conta_servico()
        try:
            _credenciais_cache = service_account.Credentials.from_service_account_info(dados, scopes=[_ESCOPO])
        except Exception as exc:
            raise RuntimeError(f"FCM_SERVICE_ACCOUNT_JSON inválido: {exc}") from exc
    return _credenciais_cache


def _access_token() -> str:
    """Access token OAuth2 (validade ~1h) — google-auth assina o JWT da conta
    de serviço, troca no endpoint do Google e cacheia/renova sozinho dentro
    do objeto Credentials (só bate na rede quando expira de verdade)."""
    creds = _credenciais()
    if not creds.valid:
        creds.refresh(GoogleAuthRequest())
    return creds.token


def project_id() -> str:
    if settings.fcm_project_id:
        return settings.fcm_project_id
    return _carregar_json_conta_servico().get("project_id", "")


class FcmTokenInvalido(Exception):
    """Token morto do lado do Firebase (UNREGISTERED / SENDER_ID_MISMATCH /
    INVALID_ARGUMENT sobre o próprio token) — quem chamou deve apagar a linha
    PushTokenFcm correspondente. Espelha o tratamento de 404/410 do Web Push
    em fazenda/api/routers/push.py::enviar_push."""


_ERROS_TOKEN_MORTO = {"UNREGISTERED", "SENDER_ID_MISMATCH"}


def enviar(token: str, titulo: str, corpo: str, url: str, count: int | None = None) -> None:
    """Manda uma notificação para UM token de registro FCM. Levanta
    FcmTokenInvalido se o Firebase disser que o token está morto; qualquer
    outra falha (rede, config, 5xx, 429) levanta a exceção original — quem
    chama (enviar_push) decide o que logar, sem propagar para o fluxo que
    decidiu o alerta."""
    if not habilitado():
        raise RuntimeError(
            "Push nativo (FCM) não configurado — defina FCM_SERVICE_ACCOUNT_JSON "
            "nas variáveis de ambiente (Firebase Console > Configurações do "
            "projeto > Contas de serviço > Gerar nova chave privada)."
        )
    dados: dict = {"url": url}
    if count is not None:
        dados["count"] = str(count)  # payload "data" do FCM só aceita string

    corpo_requisicao = {
        "message": {
            "token": token,
            # "notification" (não só "data"): é o que faz o Android desenhar
            # a notificação na bandeja com o app fechado/morto, sem código
            # nativo nosso para tratar a mensagem manualmente.
            "notification": {"title": titulo, "body": corpo},
            "data": dados,
            "android": {
                "priority": "HIGH",
                "notification": {
                    "color": "#3A0F1A",  # mesmo vinho do splash/StatusBar (capacitor.config.ts)
                    **({"notification_count": count} if count is not None else {}),
                },
            },
        }
    }
    resp = httpx.post(
        f"https://fcm.googleapis.com/v1/projects/{project_id()}/messages:send",
        headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"},
        json=corpo_requisicao,
        timeout=_TIMEOUT,
    )
    if resp.status_code >= 300:
        status_erro = ""
        try:
            status_erro = resp.json().get("error", {}).get("status", "")
        except Exception:
            pass
        if status_erro in _ERROS_TOKEN_MORTO or (resp.status_code == 404):
            raise FcmTokenInvalido(f"Token FCM inválido ({status_erro or resp.status_code})")
        raise RuntimeError(f"Falha ao enviar push via FCM: {resp.status_code} {resp.text}")
