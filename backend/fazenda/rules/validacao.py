"""Validadores de campo pequenos e compartilhados entre routers."""
from __future__ import annotations

from urllib.parse import urlparse


def link_http_seguro(link: str | None) -> str | None:
    """Aceita só `http://`/`https://` (ou vazio/None) — usado em campos de
    link livre digitados pelo usuário (link de rastreio, link de bula) que
    depois viram `<a href>` no frontend. Sem essa checagem, um valor como
    `javascript:alert(document.cookie)` executaria no navegador de quem
    clicasse, em vez de navegar para lugar nenhum."""
    if not link or not link.strip():
        return None
    link = link.strip()
    if urlparse(link).scheme not in ("http", "https"):
        raise ValueError("O link precisa começar com http:// ou https://")
    return link
