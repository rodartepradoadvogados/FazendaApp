"""WhatsApp via Evolution API (rules/whatsapp_evolution.py) — fail-closed:
sem EVOLUTION_API_URL/EVOLUTION_API_KEY/EVOLUTION_INSTANCE nenhuma chamada sai."""
import httpx
import pytest

from fazenda.config import settings
from fazenda.rules import whatsapp_evolution


@pytest.mark.parametrize("faltando", ["url", "chave", "instancia"])
def test_sem_configuracao_completa_recusa_antes_de_tocar_a_rede(monkeypatch, faltando):
    monkeypatch.setattr(settings, "evolution_api_url", "" if faltando == "url" else "https://evo.exemplo")
    monkeypatch.setattr(settings, "evolution_api_key", "" if faltando == "chave" else "chave-teste")
    monkeypatch.setattr(settings, "evolution_instance", "" if faltando == "instancia" else "fazenda-1")

    def nao_devia_chamar(*a, **k):
        raise AssertionError("httpx.post chamado sem instância Evolution configurada")

    monkeypatch.setattr(httpx, "post", nao_devia_chamar)
    with pytest.raises(RuntimeError, match="EVOLUTION_API_URL"):
        whatsapp_evolution.enviar_whatsapp("11987654321", "teste")


def test_numero_sem_digitos_recusa(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "https://evo.exemplo")
    monkeypatch.setattr(settings, "evolution_api_key", "chave-teste")
    monkeypatch.setattr(settings, "evolution_instance", "fazenda-1")

    def nao_devia_chamar(*a, **k):
        raise AssertionError("httpx.post chamado com número inválido")

    monkeypatch.setattr(httpx, "post", nao_devia_chamar)
    with pytest.raises(RuntimeError, match="inválido"):
        whatsapp_evolution.enviar_whatsapp("não é número", "teste")


def test_envio_monta_pedido_correto(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "https://evo.exemplo/")
    monkeypatch.setattr(settings, "evolution_api_key", "chave-teste")
    monkeypatch.setattr(settings, "evolution_instance", "fazenda-1")
    visto = {}

    def post(url, json, headers, timeout):
        visto.update(url=url, json=json, apikey=headers["apikey"])
        return httpx.Response(200, json={"status": "PENDING"})

    monkeypatch.setattr(httpx, "post", post)
    whatsapp_evolution.enviar_whatsapp("(11) 98765-4321", "olá")
    assert visto == {
        "url": "https://evo.exemplo/message/sendText/fazenda-1",
        "json": {"number": "11987654321", "text": "olá"},
        "apikey": "chave-teste",
    }


def test_erro_do_servidor_nao_ecoa_a_chave(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "https://evo.exemplo")
    monkeypatch.setattr(settings, "evolution_api_key", "chave-secreta")
    monkeypatch.setattr(settings, "evolution_instance", "fazenda-1")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401, text="Unauthorized"))
    with pytest.raises(RuntimeError) as e:
        whatsapp_evolution.enviar_whatsapp("11987654321", "teste")
    assert "chave-secreta" not in str(e.value)
    assert "HTTP 401" in str(e.value)
