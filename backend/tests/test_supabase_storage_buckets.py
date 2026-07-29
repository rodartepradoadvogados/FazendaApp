"""
garantir_buckets() — cria os buckets do Supabase Storage no startup se ainda
não existirem (ver fazenda/rules/supabase_storage.py). Causa real de um bug
em produção: o bucket "fotos-campo" nunca foi criado manualmente no painel
do Supabase, então todo upload falhava e a foto ficava presa na fila
offline do app, sem nunca aparecer como erro claro.
"""
from __future__ import annotations

import httpx
import pytest

from fazenda.config import settings
import fazenda.rules.supabase_storage as storage


class _RespostaFalsa:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


@pytest.fixture(autouse=True)
def _configurar_supabase(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://exemplo.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "chave-fake")
    monkeypatch.setattr(settings, "supabase_bucket", "documentos-fiscais")
    monkeypatch.setattr(settings, "supabase_bucket_fotos", "fotos-campo")


def test_sem_config_nao_faz_nada(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    chamado = {"get": False, "post": False}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: chamado.__setitem__("get", True))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: chamado.__setitem__("post", True))
    storage.garantir_buckets()
    assert chamado == {"get": False, "post": False}


def test_bucket_ja_existe_nao_cria(monkeypatch):
    chamadas_post = []
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _RespostaFalsa(200))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: chamadas_post.append(a) or _RespostaFalsa(200))
    storage.garantir_buckets()
    assert chamadas_post == []


def test_bucket_ausente_e_criado(monkeypatch):
    criados = []

    def post_fake(url, headers=None, json=None, timeout=None):
        criados.append(json["id"])
        return _RespostaFalsa(200)

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _RespostaFalsa(404, "Bucket not found"))
    monkeypatch.setattr(httpx, "post", post_fake)
    storage.garantir_buckets()
    assert set(criados) == {"documentos-fiscais", "fotos-campo"}


def test_falha_de_rede_nao_lanca(monkeypatch):
    def get_fake(*a, **k):
        raise httpx.ConnectError("fora do ar")
    monkeypatch.setattr(httpx, "get", get_fake)
    storage.garantir_buckets()  # não deve lançar — startup do app não pode cair por causa disso


def test_falha_ao_criar_nao_lanca(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _RespostaFalsa(404))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespostaFalsa(500, "erro interno"))
    storage.garantir_buckets()  # idem — só loga, não lança
