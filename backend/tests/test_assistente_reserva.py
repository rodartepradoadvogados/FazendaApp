"""Nova tentativa e modelos reserva do OpenRouter (nenhuma chamada real de rede)."""
import json

import httpx
import pytest

from fazenda.rules import assistente_llm as llm


def _resp(status, corpo):
    return httpx.Response(status, text=json.dumps(corpo), request=httpx.Request("POST", llm.URL_OPENROUTER))


OK = {"choices": [{"message": {"role": "assistant", "content": "olá"}}]}
SOBRECARGA = {"error": {"message": "Service temporarily overloaded", "code": 503}}


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setenv("ASSISTENTE_PROVEDOR", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")
    monkeypatch.setenv("ASSISTENTE_MODELO", "principal:free")
    monkeypatch.setattr(llm, "_pausar", lambda s: None)
    llm._resetar_estado_para_testes()


def _usar(monkeypatch, respostas):
    chamadas = []

    def fake(url, headers, payload, timeout):
        chamadas.append(payload["model"])
        return respostas[min(len(chamadas) - 1, len(respostas) - 1)](payload["model"])

    monkeypatch.setattr(llm, "_enviar_http", fake)
    return chamadas


def test_tenta_de_novo_o_principal_e_funciona(monkeypatch):
    chamadas = _usar(monkeypatch, [lambda m: _resp(503, SOBRECARGA), lambda m: _resp(200, OK)])
    out = llm.completar("sys", [{"role": "user", "content": "oi"}], [])
    assert out["content"] == "olá"
    assert chamadas == ["principal:free", "principal:free"]


def test_cai_para_o_modelo_reserva(monkeypatch):
    monkeypatch.setenv("ASSISTENTE_MODELOS_RESERVA", "reserva-1, reserva-2")
    chamadas = _usar(monkeypatch, [
        lambda m: _resp(503, SOBRECARGA),
        lambda m: _resp(503, SOBRECARGA),
        lambda m: _resp(200, OK),
    ])
    out = llm.completar("sys", [{"role": "user", "content": "oi"}], [])
    assert out["content"] == "olá"
    assert chamadas == ["principal:free", "principal:free", "reserva-1"]


def test_sem_reserva_continua_dando_erro_claro(monkeypatch):
    _usar(monkeypatch, [lambda m: _resp(503, SOBRECARGA)])
    with pytest.raises(llm.ErroAssistente) as e:
        llm.completar("sys", [{"role": "user", "content": "oi"}], [])
    assert e.value.tipo == "indisponivel"


def test_erro_de_chave_nao_e_repetido(monkeypatch):
    monkeypatch.setenv("ASSISTENTE_MODELOS_RESERVA", "reserva-1")
    chamadas = _usar(monkeypatch, [lambda m: _resp(401, {"error": {"message": "invalid key", "code": 401}})])
    with pytest.raises(llm.ErroAssistente) as e:
        llm.completar("sys", [{"role": "user", "content": "oi"}], [])
    assert e.value.tipo == "chave"
    assert chamadas == ["principal:free"]
