"""
Firecrawl — busca na web e leitura de páginas/PDFs públicos em markdown
(API REST v2: https://docs.firecrawl.dev/api-reference/v2-introduction).

Deixado pronto "para eventual necessidade": nenhum endpoint usa ainda. Quem
precisar (cotação do leite e notícias para o MilkNews, catálogo de touro em
página de central de genética) importa `ler_pagina` / `buscar_na_web` daqui.

Requer FIRECRAWL_API_KEY (Railway > Variables). FAIL-CLOSED: sem ela, toda
chamada levanta RuntimeError com mensagem clara — nunca tenta o plano gratuito
anônimo. Mesmo espírito de `rules/email.py` para a RESEND_API_KEY. As mensagens
de erro nunca ecoam a chave.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from fazenda.config import settings

ERRO_NAO_CONFIGURADO = (
    "Firecrawl não está configurado — falta a variável de ambiente "
    "FIRECRAWL_API_KEY. Configure-a nas variáveis do serviço (Railway > Variables) para habilitar."
)


@dataclass(frozen=True)
class PaginaLida:
    url: str
    titulo: str | None
    markdown: str


@dataclass(frozen=True)
class ResultadoBusca:
    url: str
    titulo: str | None
    descricao: str | None


def _chamar(caminho: str, corpo: dict, timeout: float) -> dict:
    chave = (settings.firecrawl_api_key or "").strip()
    if not chave:
        raise RuntimeError(ERRO_NAO_CONFIGURADO)
    base = (settings.firecrawl_api_url or "https://api.firecrawl.dev/v2").strip().rstrip("/")
    resposta = httpx.post(
        f"{base}{caminho}",
        json=corpo,
        headers={"Authorization": f"Bearer {chave}"},
        timeout=timeout,
    )
    try:
        dados = resposta.json()
    except ValueError:
        dados = None
    if resposta.status_code >= 400 or not isinstance(dados, dict) or not dados.get("success"):
        erro = dados.get("error") if isinstance(dados, dict) else None
        raise RuntimeError(f"Falha no Firecrawl {caminho} (HTTP {resposta.status_code}): {erro or 'resposta inválida'}")
    return dados


def ler_pagina(url: str, timeout: float = 60) -> PaginaLida:
    """Lê uma página pública (HTML ou documento com URL pública, ex.: PDF) e devolve o conteúdo principal em markdown."""
    dados = _chamar("/scrape", {"url": url, "formats": ["markdown"], "onlyMainContent": True}, timeout).get("data") or {}
    meta = dados.get("metadata") or {}
    return PaginaLida(url=meta.get("sourceURL") or url, titulo=meta.get("title"), markdown=dados.get("markdown") or "")


def buscar_na_web(consulta: str, limite: int = 5, timeout: float = 60) -> list[ResultadoBusca]:
    """Busca na web e devolve os resultados (sem o conteúdo; para isso, `ler_pagina` em cada URL)."""
    dados = _chamar("/search", {"query": consulta, "limit": limite}, timeout).get("data") or {}
    return [
        ResultadoBusca(url=w["url"], titulo=w.get("title"), descricao=w.get("description"))
        for w in dados.get("web") or []
    ]
