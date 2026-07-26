"""
Cliente da API do Asaas — cobrança da assinatura CowData (PIX Automático
recorrente mensal, QR Code Pix dinâmico avulso para o desconto semestral, e
boleto). Ver fazenda/models/cobranca.py::CobrancaAsaas e o router
fazenda/api/routers/asaas.py (criação de cobrança + webhook de confirmação).

Documentação: https://docs.asaas.com/ — endpoints confirmados via
documentação pública: `POST /v3/customers` (cliente), `POST /v3/payments`
(cobrança avulsa — usado para o QR Code Pix dinâmico do ciclo semestral),
`POST /v3/subscriptions` (assinatura recorrente — usado para a mensalidade).

IMPORTANTE — o endpoint específico de "Pix Automático" (autorização de
débito recorrente via Pix, distinto de uma assinatura com billingType=PIX
que gera um novo QR a cada ciclo) tem seção própria na documentação do Asaas
mas o caminho exato não foi confirmado nesta sessão (sem conta/sandbox
disponível para testar) — CONFIRME em https://docs.asaas.com/docs/pix-automatico
antes de ativar em produção. Por ora, `criar_assinatura_pix` usa
`POST /v3/subscriptions` com billingType="PIX" (assinatura Pix comum — o
Asaas gera e envia um QR novo a cada vencimento; funciona para a mensalidade,
mas não é a autorização "PIX Automático" propriamente dita).

Sem ASAAS_API_KEY configurado, toda função abaixo levanta RuntimeError com
mensagem clara — não falha silenciosamente.
"""
from __future__ import annotations

import httpx

from fazenda.config import settings

_BASE_SANDBOX = "https://api-sandbox.asaas.com/v3"
_BASE_PRODUCAO = "https://api.asaas.com/v3"


def _exigir_api_key() -> str:
    if not settings.asaas_api_key:
        raise RuntimeError(
            "Asaas não configurado — defina ASAAS_API_KEY (Asaas > Configurações > "
            "Integrações > API Key) nas variáveis de ambiente."
        )
    return settings.asaas_api_key


def _base_url() -> str:
    return _BASE_PRODUCAO if settings.asaas_ambiente == "producao" else _BASE_SANDBOX


def _headers() -> dict:
    return {"access_token": _exigir_api_key(), "Content-Type": "application/json"}


def criar_cliente(nome: str, cpf_cnpj: str, email: str | None = None) -> dict:
    """Cadastra (ou é idempotente o suficiente para reusar, ver `externalReference`
    do lado chamador) o cliente no Asaas — pré-requisito para cobrança/assinatura."""
    resp = httpx.post(
        f"{_base_url()}/customers",
        headers=_headers(),
        json={"name": nome, "cpfCnpj": cpf_cnpj, "email": email},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def criar_cobranca_pix(customer_id: str, valor: float, vencimento: str, descricao: str) -> dict:
    """Cobrança avulsa via QR Code Pix dinâmico — usado para o ciclo semestral
    (pagamento adiantado com 20% de desconto, ver DESCONTO_CICLO_PAGAMENTO).
    `vencimento` no formato YYYY-MM-DD."""
    resp = httpx.post(
        f"{_base_url()}/payments",
        headers=_headers(),
        json={"customer": customer_id, "billingType": "PIX", "value": valor, "dueDate": vencimento, "description": descricao},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def criar_cobranca_boleto(customer_id: str, valor: float, vencimento: str, descricao: str) -> dict:
    resp = httpx.post(
        f"{_base_url()}/payments",
        headers=_headers(),
        json={"customer": customer_id, "billingType": "BOLETO", "value": valor, "dueDate": vencimento, "description": descricao},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def criar_assinatura_pix(customer_id: str, valor: float, proximo_vencimento: str, descricao: str) -> dict:
    """Assinatura mensal recorrente — o Asaas gera e cobra (via QR/link) a cada
    vencimento automaticamente. Ver nota no topo do arquivo sobre a diferença
    para o "Pix Automático" (autorização de débito, não confirmada aqui)."""
    resp = httpx.post(
        f"{_base_url()}/subscriptions",
        headers=_headers(),
        json={"customer": customer_id, "billingType": "PIX", "value": valor, "nextDueDate": proximo_vencimento, "cycle": "MONTHLY", "description": descricao},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def consultar_cobranca(payment_id: str) -> dict:
    """Busca o status de uma cobrança DIRETO na API do Asaas — usado pelo
    webhook para re-confirmar o pagamento server-to-server antes de liberar
    qualquer acesso (nunca confiar só no corpo do webhook, ver
    fazenda/api/routers/asaas.py::asaas_webhook)."""
    resp = httpx.get(f"{_base_url()}/payments/{payment_id}", headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()
