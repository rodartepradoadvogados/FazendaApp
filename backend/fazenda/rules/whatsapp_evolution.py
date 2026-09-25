"""
WhatsApp via Evolution API — conector NÃO-OFICIAL (Baileys/QR code, mesmo
mecanismo do WhatsApp Web: o número é o de quem escaneou o QR code na
instância, não um número de Business API homologado pela Meta).

Risco registrado, para quem for configurar isto em produção: usar um cliente
não-oficial viola os Termos de Serviço do WhatsApp — o sistema antifraude da
Meta costuma detectar esse tipo de conexão em algumas semanas de uso, e o
banimento do número é permanente, sem recurso. Recomendação já passada ao
usuário: validar o fluxo com um número não crítico antes de conectar o número
principal da fazenda. A Evolution API também tem um conector para a Cloud API
oficial da Meta, caso decida migrar para o caminho homologado depois — esta
função não depende de qual dos dois a instância está usando, só fala com a
API REST do servidor Evolution.

FAIL-CLOSED: sem EVOLUTION_API_URL / EVOLUTION_API_KEY / EVOLUTION_INSTANCE,
toda chamada levanta RuntimeError — nunca tenta enviar sem instância
configurada. Mesmo espírito de rules/firecrawl.py e rules/email.py. A mensagem
de erro nunca ecoa a chave.
"""
from __future__ import annotations

import httpx

from fazenda.config import settings

ERRO_NAO_CONFIGURADO = (
    "WhatsApp (Evolution API) não está configurado — faltam as variáveis de ambiente "
    "EVOLUTION_API_URL, EVOLUTION_API_KEY e EVOLUTION_INSTANCE. Configure-as nas variáveis "
    "do serviço (Railway > Variables) para habilitar o envio."
)


def _somente_digitos(numero: str) -> str:
    return "".join(c for c in numero if c.isdigit())


def enviar_whatsapp(numero: str, texto: str, timeout: float = 20) -> None:
    """Envia uma mensagem de texto livre pelo número conectado na instância
    Evolution configurada. `numero` aceita qualquer formatação (máscara,
    espaços, +55...) — só os dígitos importam. Não bloqueia por rate limit
    nem tenta novamente sozinha; quem chama decide o que fazer com o erro
    (ex.: marcar `status_envio="falha_envio"` e deixar visível pro gestor)."""
    url = (settings.evolution_api_url or "").strip()
    chave = (settings.evolution_api_key or "").strip()
    instancia = (settings.evolution_instance or "").strip()
    if not url or not chave or not instancia:
        raise RuntimeError(ERRO_NAO_CONFIGURADO)

    numero_limpo = _somente_digitos(numero)
    if not numero_limpo:
        raise RuntimeError("Número de WhatsApp inválido — sem nenhum dígito.")

    resposta = httpx.post(
        f"{url.rstrip('/')}/message/sendText/{instancia}",
        json={"number": numero_limpo, "text": texto},
        headers={"apikey": chave},
        timeout=timeout,
    )
    if resposta.status_code >= 400:
        raise RuntimeError(f"Falha ao enviar WhatsApp (HTTP {resposta.status_code}): {resposta.text[:200]}")
