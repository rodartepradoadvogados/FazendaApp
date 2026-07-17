"""
fazenda.rules.news_fetch — busca de notícias com fallback para o Google
Notícias quando a fonte cadastrada bloqueia acesso automatizado direto
(proteção anti-bot, comum nos grandes portais de agro). Usa httpx.MockTransport
para nunca depender de rede de verdade.
"""
from __future__ import annotations

import httpx
import pytest

from fazenda.rules import news_fetch

RSS_OK = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>Preco do leite sobe, diz Cepea</title>
  <description>A pecuaria leiteira teve alta nos precos ao produtor.</description>
  <link>https://exemplo.com/noticia-1</link>
  <pubDate>Wed, 15 Jul 2026 10:00:00 GMT</pubDate>
</item>
</channel></rss>"""

RSS_GOOGLE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>Ordenha robotizada cresce no Brasil</title>
  <description>Free stall e compost barn ganham espaco.</description>
  <link>https://news.google.com/rss/articles/xyz</link>
  <pubDate>Wed, 15 Jul 2026 09:00:00 GMT</pubDate>
</item>
</channel></rss>"""


def _client_com_transporte(monkeypatch, handler):
    """Faz `httpx.Client(...)` (chamado de dentro de news_fetch) usar um
    MockTransport, sem mexer na assinatura de buscar_noticias_fonte."""
    transporte = httpx.MockTransport(handler)
    original = httpx.Client

    def _client_falso(*args, **kwargs):
        kwargs["transport"] = transporte
        return original(*args, **kwargs)

    monkeypatch.setattr(news_fetch.httpx, "Client", _client_falso)


class TestBuscarNoticiasFonte:
    def test_direto_funciona_sem_cair_no_google(self, monkeypatch):
        chamadas = []

        def handler(request: httpx.Request) -> httpx.Response:
            chamadas.append(str(request.url))
            return httpx.Response(200, content=RSS_OK, headers={"content-type": "application/rss+xml"})

        _client_com_transporte(monkeypatch, handler)
        itens = news_fetch.buscar_noticias_fonte("https://www.exemplo.com.br/feed")
        assert len(itens) == 1
        assert itens[0]["manchete"] == "Preco do leite sobe, diz Cepea"
        assert all("news.google.com" not in c for c in chamadas)

    def test_cai_para_google_noticias_quando_direto_bloqueia(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            if "news.google.com" in str(request.url):
                assert "site%3Aexemplo.com.br" in str(request.url) or "site=exemplo.com.br" in str(request.url).replace("%3A", "=")
                return httpx.Response(200, content=RSS_GOOGLE, headers={"content-type": "application/rss+xml"})
            return httpx.Response(403, content="blocked")

        _client_com_transporte(monkeypatch, handler)
        itens = news_fetch.buscar_noticias_fonte("https://www.exemplo.com.br/")
        assert len(itens) == 1
        assert itens[0]["manchete"] == "Ordenha robotizada cresce no Brasil"

    def test_erro_quando_direto_e_google_falham(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, content="blocked")

        _client_com_transporte(monkeypatch, handler)
        with pytest.raises(RuntimeError):
            news_fetch.buscar_noticias_fonte("https://www.exemplo.com.br/")

    def test_falha_de_conexao_tambem_cai_para_google(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            if "news.google.com" in str(request.url):
                return httpx.Response(200, content=RSS_GOOGLE, headers={"content-type": "application/rss+xml"})
            raise httpx.ConnectError("falha de rede simulada", request=request)

        _client_com_transporte(monkeypatch, handler)
        itens = news_fetch.buscar_noticias_fonte("https://www.exemplo.com.br/")
        assert len(itens) == 1


class TestUrlGoogleNews:
    def test_dominio_br_usa_locale_pt_br(self):
        url = news_fetch._url_google_news("milkpoint.com.br")
        assert "hl=pt-BR" in url
        assert "gl=BR" in url
        assert "ceid=BR:pt-419" in url

    def test_dominio_internacional_usa_locale_en_us(self):
        url = news_fetch._url_google_news("dairyreporter.com")
        assert "hl=en-US" in url
        assert "gl=US" in url
        assert "ceid=US:en" in url
