"""
Busca de notícias para o agregador "News" (blog de pecuária leiteira).

Cada fonte cadastrada (Configurações > News, só administrador) é buscada como
feed RSS/Atom — direto na URL cadastrada, ou descoberto a partir do
<link rel="alternate" type="application/rss+xml"> da página, quando a URL
cadastrada é a home do site em vez do feed em si. Nunca baixa o texto
integral da matéria: só manchete, resumo (description/summary do próprio
feed) e o link para a fonte original, respeitando direito autoral.

Uma fonte que falhar (rede, HTTP, layout sem feed) levanta RuntimeError com
uma mensagem curta — o chamador (fazenda.api.routers.news) grava isso em
FonteNews.ultimo_erro para o administrador ver e substituir/corrigir a URL,
sem derrubar as outras fontes nem a página toda.
"""
from __future__ import annotations

import html as html_lib
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx

TIMEOUT = httpx.Timeout(15.0)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FazendaAppNewsBot/1.0; +https://fazenda-app-jfye.vercel.app/)"}

# Palavras-chave do setor (normalizadas: minúsculas, sem acento) — uma matéria
# só entra se manchete+resumo citarem pelo menos uma delas.
PALAVRAS_CHAVE = [
    "leite", "produtor de leite", "pecuaria leiteira", "ordenha", "compost barn", "free stall",
]

RESUMO_MAX = 500

_TAG_RE = re.compile(r"<[^>]+>")
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""(\w[\w-]*)\s*=\s*"([^"]*)"|(\w[\w-]*)\s*=\s*'([^']*)'""")


def _normalizar(texto: str) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower()


def _relevante(manchete: str, resumo: str | None) -> bool:
    texto = _normalizar(f"{manchete} {resumo or ''}")
    return any(p in texto for p in PALAVRAS_CHAVE)


def filtrar_relevantes(itens: list[dict]) -> list[dict]:
    return [item for item in itens if _relevante(item["manchete"], item.get("resumo"))]


def _limpar_html(texto: str) -> str:
    sem_tags = _TAG_RE.sub(" ", texto or "")
    sem_tags = html_lib.unescape(sem_tags)
    sem_tags = re.sub(r"\s+", " ", sem_tags).strip()
    if len(sem_tags) > RESUMO_MAX:
        sem_tags = sem_tags[: RESUMO_MAX - 1].rstrip() + "…"
    return sem_tags


def _parse_data(valor: str | None) -> datetime | None:
    """Datas de feed vêm em formatos variados (RFC 822 no RSS, ISO 8601 no
    Atom) — normaliza tudo para UTC ingênuo (sem tzinfo), igual ao resto do
    banco (datetime.utcnow()), para dar pra comparar sem erro."""
    if not valor:
        return None
    valor = valor.strip()
    dt = None
    try:
        dt = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(valor, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extrair_itens_xml(conteudo: bytes) -> list[dict] | None:
    """RSS 2.0 (<item>) ou Atom (<entry>). None quando o conteúdo não é XML
    (a URL cadastrada era a home do site, não o feed)."""
    try:
        root = ET.fromstring(conteudo)
    except ET.ParseError:
        return None

    itens: list[dict] = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        titulo: str | None = None
        resumo: str | None = None
        resumo_fallback: str | None = None
        link: str | None = None
        data_bruta: str | None = None
        for child in el:
            tag = _local(child.tag)
            if tag == "title" and titulo is None:
                titulo = _limpar_html(child.text or "")
            elif tag in ("description", "summary") and resumo is None:
                resumo = _limpar_html(child.text or "")
            elif tag == "content" and resumo_fallback is None:
                resumo_fallback = _limpar_html(child.text or "")
            elif tag == "link" and link is None:
                href = child.get("href") or child.text
                if href:
                    link = href.strip()
            elif tag in ("pubDate", "published", "updated") and data_bruta is None:
                data_bruta = child.text
        if titulo and link:
            itens.append({
                "manchete": titulo, "resumo": resumo or resumo_fallback, "link": link,
                "data": _parse_data(data_bruta),
            })
    return itens or None


def _descobrir_feed(html_texto: str, base_url: str) -> str | None:
    for tag in _LINK_TAG_RE.findall(html_texto):
        attrs: dict[str, str] = {}
        for m in _ATTR_RE.finditer(tag):
            if m.group(1):
                attrs[m.group(1).lower()] = m.group(2)
            else:
                attrs[m.group(3).lower()] = m.group(4)
        tipo = (attrs.get("type") or "").lower()
        href = attrs.get("href")
        if href and ("rss" in tipo or "atom" in tipo):
            return urljoin(base_url, href)
    return None


def buscar_noticias_fonte(url: str) -> list[dict]:
    """Busca uma fonte e retorna os itens (manchete/resumo/link/data), sem
    filtrar por relevância ainda. Levanta RuntimeError com mensagem curta em
    qualquer falha (rede, HTTP, ou site sem feed localizável)."""
    with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        try:
            resp = client.get(url)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Falha ao conectar: {exc}") from exc
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code} ao acessar o site")

        itens = _extrair_itens_xml(resp.content)
        if itens is None:
            feed_url = _descobrir_feed(resp.text, str(resp.url))
            if feed_url and feed_url != url:
                try:
                    resp2 = client.get(feed_url)
                except httpx.HTTPError as exc:
                    raise RuntimeError(f"Falha ao conectar ao feed: {exc}") from exc
                if resp2.status_code < 400:
                    itens = _extrair_itens_xml(resp2.content)
        if itens is None:
            raise RuntimeError("Não foi possível localizar um feed RSS/Atom válido neste site — cadastre a URL do feed diretamente")
    return itens
