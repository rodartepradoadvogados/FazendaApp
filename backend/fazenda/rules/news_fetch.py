"""
Busca de notícias para o agregador "News" (blog de pecuária leiteira).

Cada fonte cadastrada (Configurações > News, só administrador) é buscada em
duas tentativas:
  1. Direto na URL cadastrada — como feed RSS/Atom, ou descoberto a partir do
     <link rel="alternate" type="application/rss+xml"> da página, quando a
     URL cadastrada é a home do site em vez do feed em si.
  2. Se a primeira falhar (muitos desses sites bloqueiam requisição de
     servidor por trás de proteção anti-bot — Cloudflare e afins — mesmo com
     cabeçalhos de navegador), cai no feed RSS público do Google Notícias
     filtrado por `site:<domínio>`, que não depende do site original liberar
     acesso automatizado. Mesmo formato RSS 2.0, reaproveita o mesmo parser.
Nunca baixa o texto integral da matéria: só manchete, resumo (description/
summary do próprio feed) e o link para a fonte original, respeitando direito
autoral.

Uma fonte que falhar nas duas tentativas levanta RuntimeError com uma
mensagem curta — o chamador (fazenda.api.routers.news) grava isso em
FonteNews.ultimo_erro para o administrador ver e substituir/corrigir a URL,
sem derrubar as outras fontes nem a página toda.
"""
from __future__ import annotations

import html as html_lib
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx

TIMEOUT = httpx.Timeout(15.0)
# Cabeçalhos de navegador de verdade — várias dessas fontes usam proteção
# anti-bot (Cloudflare e afins) que bloqueia um User-Agent que se identifica
# como bot, mesmo sem nenhum comportamento abusivo por trás.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# Fallback via Google Notícias (RSS público, sem chave de API) — usado quando
# a fonte cadastrada bloqueia acesso automatizado direto. `when:Nd` já limita
# a busca aos últimos N dias na origem, além do filtro de janela feito depois
# em fazenda.api.routers.news.
GOOGLE_NEWS_JANELA_DIAS = 7


def _locale_por_dominio(dominio: str) -> tuple[str, str, str]:
    """(hl, gl, ceid) do Google Notícias — português/Brasil para domínios
    .br, inglês/EUA para o resto (as duas fontes internacionais cadastradas)."""
    if dominio.endswith(".br"):
        return "pt-BR", "BR", "BR:pt-419"
    return "en-US", "US", "US:en"


def _url_google_news(dominio: str) -> str:
    hl, gl, ceid = _locale_por_dominio(dominio)
    query = quote(f"site:{dominio} when:{GOOGLE_NEWS_JANELA_DIAS}d")
    return f"https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"

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


def _tentar_direto(client: httpx.Client, url: str) -> tuple[list[dict] | None, str | None]:
    """1ª tentativa: a URL cadastrada, como feed direto ou com autodescoberta
    de feed na página. Retorna (itens, None) OU (None, motivo_da_falha) —
    nunca levanta, para o chamador poder cair no fallback do Google Notícias."""
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        return None, f"Falha ao conectar: {exc}"
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code} ao acessar o site"

    itens = _extrair_itens_xml(resp.content)
    if itens is None:
        feed_url = _descobrir_feed(resp.text, str(resp.url))
        if feed_url and feed_url != url:
            try:
                resp2 = client.get(feed_url)
            except httpx.HTTPError:
                feed_url = None
            else:
                if resp2.status_code < 400:
                    itens = _extrair_itens_xml(resp2.content)
        if itens is None:
            return None, "Não foi possível localizar um feed RSS/Atom válido nesta URL"
    return itens, None


def _tentar_google_news(client: httpx.Client, url: str) -> list[dict] | None:
    """2ª tentativa: feed RSS público do Google Notícias filtrado por
    site:<domínio> — funciona mesmo quando o site original bloqueia acesso
    automatizado (proteção anti-bot), já que quem responde é o Google."""
    dominio = urlparse(url).netloc.removeprefix("www.")
    if not dominio:
        return None
    try:
        resp = client.get(_url_google_news(dominio))
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    return _extrair_itens_xml(resp.content)


def buscar_noticias_fonte(url: str) -> list[dict]:
    """Busca uma fonte e retorna os itens (manchete/resumo/link/data), sem
    filtrar por relevância ainda. Tenta a URL cadastrada primeiro; se falhar,
    cai no Google Notícias filtrado por esse domínio. Levanta RuntimeError com
    mensagem curta só se as duas tentativas falharem."""
    with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        itens, motivo = _tentar_direto(client, url)
        if itens:
            return itens
        itens_google = _tentar_google_news(client, url)
        if itens_google:
            return itens_google
        raise RuntimeError(motivo or "Não foi possível buscar notícias desta fonte (direto ou via Google Notícias)")
