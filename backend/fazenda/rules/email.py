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


def enviar_email(
    destinatario: str, assunto: str, corpo_html: str, anexo_nome: str | None = None, anexo_bytes: bytes | None = None,
    *, anexos_extras: list[tuple[str, bytes]] | None = None,
) -> None:
    """Envia um e-mail via Resend — com um anexo (ex.: PDF do recibo)
    quando anexo_nome/anexo_bytes são informados, ou só o corpo HTML (ex.:
    resumo do diagnóstico de gestação) quando não são. `anexos_extras`
    ([(nome, bytes)]) acrescenta outros anexos depois do primeiro (ex.: a DRE
    no CSV antigo e no novo, Fase A PR 8)."""
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
    anexos = ([(anexo_nome, anexo_bytes)] if anexo_nome and anexo_bytes else []) + list(anexos_extras or [])
    if anexos:
        payload["attachments"] = [{
            "filename": nome,
            "content": base64.standard_b64encode(conteudo).decode("utf-8"),
        } for nome, conteudo in anexos if nome and conteudo]
    resposta = httpx.post(
        RESEND_API,
        json=payload,
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        timeout=30,
    )
    if resposta.status_code >= 400:
        raise RuntimeError(f"Falha ao enviar e-mail (Resend): {resposta.text}")
