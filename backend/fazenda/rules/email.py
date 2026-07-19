"""
Envio de e-mail (recibo de lançamento financeiro) via Resend.

Requer a variável de ambiente RESEND_API_KEY (Railway > Variables). Sem ela,
`enviar_email` levanta RuntimeError com uma mensagem clara para o
administrador configurar — mesmo espírito de `rules/leitura_documento.py`
para a ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import base64

import httpx

from fazenda.config import settings

RESEND_API = "https://api.resend.com/emails"


def enviar_email(destinatario: str, assunto: str, corpo_html: str, anexo_nome: str | None = None, anexo_bytes: bytes | None = None) -> None:
    """Envia um e-mail via Resend — com um único anexo (ex.: PDF do recibo)
    quando anexo_nome/anexo_bytes são informados, ou só o corpo HTML (ex.:
    resumo do diagnóstico de gestação) quando não são."""
    if not settings.resend_api_key:
        raise RuntimeError(
            "Envio de e-mail não está configurado — falta a variável de ambiente "
            "RESEND_API_KEY. Configure-a nas variáveis do serviço (Railway > Variables) para habilitar."
        )
    payload = {
        "from": settings.email_remetente,
        "to": [destinatario],
        "subject": assunto,
        "html": corpo_html,
    }
    if anexo_nome and anexo_bytes:
        payload["attachments"] = [{
            "filename": anexo_nome,
            "content": base64.standard_b64encode(anexo_bytes).decode("utf-8"),
        }]
    resposta = httpx.post(
        RESEND_API,
        json=payload,
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        timeout=30,
    )
    if resposta.status_code >= 400:
        raise RuntimeError(f"Falha ao enviar e-mail (Resend): {resposta.text}")
