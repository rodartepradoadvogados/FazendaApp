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


# ---------------------------------------------------------------------------
# Failover rápido + orçamento de tempo (17/10/2026 — o chat pendurava
# minutos porque o principal `:free` saturado segurava 90s por tentativa
# antes de o reserva, que poderia responder, ser sequer tentado).
# ---------------------------------------------------------------------------
def test_principal_e_tentado_com_timeout_curto_reserva_com_timeout_cheio(monkeypatch):
    monkeypatch.setenv("ASSISTENTE_MODELOS_RESERVA", "reserva-1")
    tempos = []

    def fake(url, headers, payload, timeout):
        tempos.append(timeout)
        return _resp(503, SOBRECARGA) if len(tempos) < 3 else _resp(200, OK)

    monkeypatch.setattr(llm, "_enviar_http", fake)
    out = llm.completar("sys", [{"role": "user", "content": "oi"}], [])
    assert out["content"] == "olá"
    assert tempos[0] == llm.TIMEOUT_TENTATIVA_PRINCIPAL_S
    assert tempos[1] == llm.TIMEOUT_TENTATIVA_PRINCIPAL_S
    # reserva entra com o teto normal (ou o que restar do orçamento)
    assert tempos[2] > llm.TIMEOUT_TENTATIVA_PRINCIPAL_S
    assert tempos[2] <= llm.TIMEOUT_SEGUNDOS


def test_orcamento_esgotado_desiste_sem_abrir_chamada_nova(monkeypatch):
    monkeypatch.setenv("ASSISTENTE_MODELOS_RESERVA", "reserva-1, reserva-2")
    # relógio falso: 0s no início, +100s a cada checagem de orçamento —
    # na 3a leitura (200s) o orçamento de 150s já estourou e reserva-1 nem é tentado
    monkeypatch.setattr(llm, "_mono", iter([0.0, 100.0, 200.0, 300.0]).__next__)
    modelos_chamados = []

    def fake(url, headers, payload, timeout):
        modelos_chamados.append(payload["model"])
        return _resp(503, SOBRECARGA)

    monkeypatch.setattr(llm, "_enviar_http", fake)
    with pytest.raises(llm.ErroAssistente) as e:
        llm.completar("sys", [{"role": "user", "content": "oi"}], [])
    assert e.value.tipo == "indisponivel"
    assert modelos_chamados == ["principal:free", "principal:free"]
