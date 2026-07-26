"""
Cliente da API do Banco do Brasil (Cobranças/boleto + PIX) — cobrança da
mensalidade CowData (ver fazenda/models/cobranca.py e o router
fazenda/api/routers/cobranca.py). Cadastro de app developer em
https://developers.bb.com.br/ (Cobranças + PIX) — ver ZAPSIGN_API_TOKEN em
fazenda/config.py para o mesmo padrão usado no ZapSign.

IMPORTANTE — não validado contra o sandbox real do BB (sem credenciais dev
disponíveis nesta sessão): os nomes de endpoint/campo abaixo seguem a
documentação pública estável da API "Cobranças" e "PIX" do BB, mas PRECISAM
ser conferidos contra o Portal Developers (https://developers.bb.com.br/)
antes do primeiro uso em produção — sobretudo os campos do `pagador`/`devedor`
e o nome exato de cada query/header. Sem BB_CLIENT_ID/BB_CLIENT_SECRET
configurados, toda função abaixo levanta RuntimeError com mensagem clara.
"""
from __future__ import annotations

import base64
import time
from datetime import date

import httpx

from fazenda.config import settings

_TOKEN_CACHE: dict = {"access_token": None, "expira_em": 0}


def _exigir_credenciais() -> None:
    if not (settings.bb_client_id and settings.bb_client_secret and settings.bb_developer_application_key):
        raise RuntimeError(
            "Banco do Brasil não configurado — defina BB_CLIENT_ID, BB_CLIENT_SECRET e "
            "BB_DEVELOPER_APPLICATION_KEY (conta developer em https://developers.bb.com.br/, "
            "apps Cobranças + PIX) nas variáveis de ambiente."
        )


def _base_url() -> str:
    return "https://api.bb.com.br" if settings.bb_ambiente == "producao" else "https://api.sandbox.bb.com.br"


def _oauth_url() -> str:
    return "https://oauth.bb.com.br/oauth/token" if settings.bb_ambiente == "producao" else "https://oauth.sandbox.bb.com.br/oauth/token"


def _obter_token(scope: str) -> str:
    """Token OAuth2 client_credentials, cacheado em memória do processo até
    expirar (evita pedir um token novo a cada chamada)."""
    _exigir_credenciais()
    agora = time.time()
    if _TOKEN_CACHE["access_token"] and agora < _TOKEN_CACHE["expira_em"] - 30:
        return _TOKEN_CACHE["access_token"]

    credenciais = base64.b64encode(f"{settings.bb_client_id}:{settings.bb_client_secret}".encode()).decode()
    resp = httpx.post(
        _oauth_url(),
        headers={"Authorization": f"Basic {credenciais}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": scope},
        timeout=30,
    )
    resp.raise_for_status()
    dados = resp.json()
    _TOKEN_CACHE["access_token"] = dados["access_token"]
    _TOKEN_CACHE["expira_em"] = agora + dados.get("expires_in", 600)
    return _TOKEN_CACHE["access_token"]


def emitir_boleto(numero_convenio: str, valor: float, data_vencimento: date, pagador_nome: str, pagador_documento: str) -> dict:
    """Registra um boleto na API "Cobranças" do BB. Devolve o JSON cru da
    resposta (nossoNumero, linhaDigitável, codigoBarraNumerico, etc — nomes
    exatos a conferir no Portal Developers antes de usar em produção)."""
    token = _obter_token("cobrancas.boletos-requisicao cobrancas.boletos-info")
    resp = httpx.post(
        f"{_base_url()}/cobrancas/v2/boletos",
        params={"gw-dev-app-key": settings.bb_developer_application_key},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "numeroConvenio": numero_convenio,
            "dataEmissao": date.today().strftime("%d.%m.%Y"),
            "dataVencimento": data_vencimento.strftime("%d.%m.%Y"),
            "valorOriginal": valor,
            "codigoAceite": "N",
            "codigoTipoTitulo": "2",
            "pagador": {
                "tipoInscricao": 2 if len(pagador_documento) > 11 else 1,
                "numeroInscricao": pagador_documento,
                "nome": pagador_nome,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def emitir_cobranca_pix(txid: str, valor: float, chave_recebedora: str | None = None, expiracao_segundos: int = 3600) -> dict:
    """Cria uma cobrança PIX imediata (`PUT /pix/v2/cob/{txid}`). Devolve o
    JSON cru — `pixCopiaECola` é a string "copia e cola"; o QR code é gerado
    a partir do payload `location`/`brcode` retornado (ver documentação PIX
    do BC/BB para o encode em imagem — não incluso aqui)."""
    token = _obter_token("cob.write cob.read")
    resp = httpx.put(
        f"{_base_url()}/pix/v2/cob/{txid}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "calendario": {"expiracao": expiracao_segundos},
            "valor": {"original": f"{valor:.2f}"},
            "chave": chave_recebedora or settings.bb_pix_chave,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
