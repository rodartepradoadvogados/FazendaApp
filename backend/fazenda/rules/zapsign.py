"""
Cliente da API do ZapSign (assinatura eletrônica do contrato CowData) — ver
fazenda/templates/contrato_cowdata.md (conteúdo enviado via `markdown_text`,
sem precisar gerar PDF) e fazenda/api/routers/zapsign.py (webhook de status).

Documentação: https://docs.zapsign.com.br/ — endpoint `POST /api/v1/docs/`
(criação) e `GET /api/v1/docs/{token}/` (status). Token de API em
Configurações > Integrações > API ZAPSIGN no painel ZapSign; configurar em
ZAPSIGN_API_TOKEN (ver fazenda/config.py). Sem token configurado, as funções
abaixo levantam RuntimeError com mensagem clara — não falham silenciosamente.
"""
from __future__ import annotations

import httpx

from fazenda.config import settings

_BASE_URL = "https://api.zapsign.com.br/api/v1/docs/"


def _exigir_token() -> str:
    if not settings.zapsign_api_token:
        raise RuntimeError(
            "ZapSign não configurado — defina ZAPSIGN_API_TOKEN (Configurações > "
            "Integrações > API ZAPSIGN no painel ZapSign) nas variáveis de ambiente."
        )
    return settings.zapsign_api_token


def criar_documento_para_assinatura(nome_documento: str, markdown_text: str, signer_nome: str, signer_email: str) -> dict:
    """Cria o documento no ZapSign a partir do texto do contrato e devolve a
    resposta crua da API (token do documento, status, e o sign_url do
    signatário — ver ContratoAssinaturaZapSign em fazenda/models/planos.py)."""
    token = _exigir_token()
    resp = httpx.post(
        _BASE_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "name": nome_documento[:255],
            "markdown_text": markdown_text,
            "signers": [{
                "name": signer_nome,
                "email": signer_email,
                "auth_mode": "tokenEmail",
                "send_automatic_email": True,
            }],
            "signature_order_active": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def consultar_status_documento(document_token: str) -> dict:
    token = _exigir_token()
    resp = httpx.get(
        f"{_BASE_URL}{document_token}/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
