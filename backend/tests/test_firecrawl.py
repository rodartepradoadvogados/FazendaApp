"""Firecrawl (rules/firecrawl.py) — fail-closed: sem FIRECRAWL_API_KEY nenhuma chamada sai."""
import httpx
import pytest

from fazenda.config import settings
from fazenda.rules import firecrawl


@pytest.mark.parametrize("chave", ["", "   "])
def test_sem_chave_recusa_antes_de_tocar_a_rede(monkeypatch, chave):
    monkeypatch.setattr(settings, "firecrawl_api_key", chave)

    def nao_devia_chamar(*a, **k):
        raise AssertionError("httpx.post chamado sem chave configurada")

    monkeypatch.setattr(httpx, "post", nao_devia_chamar)
    with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
        firecrawl.ler_pagina("https://exemplo.com")
    with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
        firecrawl.buscar_na_web("cotação do leite")


def test_busca_monta_pedido_e_le_resposta(monkeypatch):
    monkeypatch.setattr(settings, "firecrawl_api_key", "fc-teste")
    monkeypatch.setattr(settings, "firecrawl_api_url", "https://fc.exemplo/v2/")
    visto = {}

    def post(url, json, headers, timeout):
        visto.update(url=url, json=json, auth=headers["Authorization"])
        return httpx.Response(200, json={"success": True, "data": {"web": [
            {"url": "https://a.exemplo", "title": "A", "description": "d"},
        ]}})

    monkeypatch.setattr(httpx, "post", post)
    r = firecrawl.buscar_na_web("leite", limite=1)
    assert visto == {"url": "https://fc.exemplo/v2/search", "json": {"query": "leite", "limit": 1}, "auth": "Bearer fc-teste"}
    assert [(x.url, x.titulo, x.descricao) for x in r] == [("https://a.exemplo", "A", "d")]


def test_erro_do_firecrawl_nao_ecoa_a_chave(monkeypatch):
    monkeypatch.setattr(settings, "firecrawl_api_key", "fc-segredo")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401, json={"success": False, "error": "Unauthorized"}))
    with pytest.raises(RuntimeError) as e:
        firecrawl.ler_pagina("https://exemplo.com")
    assert "fc-segredo" not in str(e.value)
    assert "HTTP 401" in str(e.value)
