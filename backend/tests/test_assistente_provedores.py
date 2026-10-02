"""
Motor do Assistente por provedor (OpenRouter / Anthropic) + mapeamento de
erros — ver fazenda/rules/assistente_llm.py. NENHUMA chamada real de rede:
o OpenRouter é simulado trocando `assistente_llm._enviar_http`, e a Anthropic
trocando `anthropic.Anthropic`.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Animal, ContratoFazenda, Fazenda
from fazenda.rules import assistente_llm as llm
from fazenda.rules.assistente import (
    _ferramentas_do_usuario,
    responder,
)

CHAVE_FALSA = "sk-or-v1-CHAVE-SECRETA-DE-TESTE-1234567890"


class _Usuario:
    def __init__(self, papel="admin", permissoes=""):
        self.id = 1
        self.papel = papel
        self.permissoes = permissoes
        self.ativo = True
        self.username = "teste"


@pytest.fixture(autouse=True)
def _ambiente_limpo(monkeypatch):
    for v in ("ASSISTENTE_PROVEDOR", "ASSISTENTE_MODELO", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    llm._resetar_estado_para_testes()


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(Animal(numero="500", nome="Estrela", sexo="F", raca="Girolando", fazenda_id=1))
        s.commit()
    return eng


@pytest.fixture
def client(engine):
    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id
    import fazenda.database as database

    def _sess():
        with Session(engine) as s:
            yield s

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _Usuario(papel="admin")
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _resp_http(status=200, corpo=None, texto=None):
    req = httpx.Request("POST", llm.URL_OPENROUTER)
    if texto is not None:
        return httpx.Response(status, text=texto, request=req)
    return httpx.Response(status, json=corpo if corpo is not None else {}, request=req)


def _msg_openrouter(content=None, tool_calls=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg, "finish_reason": finish}]}


def _tool_call(nome, args, id_="call_1"):
    return {"id": id_, "type": "function", "function": {"name": nome, "arguments": json.dumps(args)}}


# ---------------------------------------------------------------------------
# Escolha do provedor / modelo / configuração
# ---------------------------------------------------------------------------
class TestConfiguracao:
    def test_sem_nenhuma_chave_e_erro_de_configuracao_claro(self):
        cfg = llm.configuracao()
        assert cfg["configurado"] is False
        with pytest.raises(llm.ErroAssistente) as e:
            llm.completar("sys", [{"role": "user", "content": "oi"}], [])
        assert e.value.tipo == "configuracao"
        assert "OPENROUTER_API_KEY" in str(e.value) and "ANTHROPIC_API_KEY" in str(e.value)

    def test_so_openrouter_key_escolhe_openrouter(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        cfg = llm.configuracao()
        assert (cfg["provedor"], cfg["modelo"], cfg["configurado"]) == ("openrouter", "anthropic/claude-sonnet-4.5", True)

    def test_so_anthropic_key_escolhe_anthropic(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
        cfg = llm.configuracao()
        assert (cfg["provedor"], cfg["modelo"], cfg["configurado"]) == ("anthropic", "claude-sonnet-5", True)

    def test_com_as_duas_chaves_openrouter_ganha(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
        assert llm.configuracao()["provedor"] == "openrouter"

    def test_provedor_explicito_vence_a_ordem_automatica(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
        monkeypatch.setenv("ASSISTENTE_PROVEDOR", "anthropic")
        assert llm.configuracao()["provedor"] == "anthropic"

    def test_provedor_explicito_sem_a_chave_dele_nao_cai_no_outro(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
        monkeypatch.setenv("ASSISTENTE_PROVEDOR", "openrouter")
        cfg = llm.configuracao()
        assert cfg["provedor"] == "openrouter" and cfg["configurado"] is False

    def test_provedor_invalido_e_erro_de_configuracao(self, monkeypatch):
        monkeypatch.setenv("ASSISTENTE_PROVEDOR", "gemini")
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        assert llm.configuracao()["configurado"] is False
        with pytest.raises(llm.ErroAssistente) as e:
            llm.completar("s", [{"role": "user", "content": "oi"}], [])
        assert e.value.tipo == "configuracao"
        assert "ASSISTENTE_PROVEDOR" in str(e.value)

    def test_modelo_por_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setenv("ASSISTENTE_MODELO", "openai/gpt-4.1")
        assert llm.configuracao()["modelo"] == "openai/gpt-4.1"

    def test_status_nao_vaza_a_chave(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        assert CHAVE_FALSA not in json.dumps(llm.status_assistente())


# ---------------------------------------------------------------------------
# Conversão de schema Anthropic -> OpenAI
# ---------------------------------------------------------------------------
class TestSchema:
    def test_input_schema_vira_parameters(self):
        spec = {"name": "buscar_animal", "description": "d", "input_schema": {
            "type": "object", "properties": {"numero": {"type": "string"}}, "required": ["numero"],
            "additionalProperties": False}}
        out = llm.ferramenta_para_openai(spec)
        assert out == {"type": "function", "function": {
            "name": "buscar_animal", "description": "d",
            "parameters": {"type": "object", "properties": {"numero": {"type": "string"}},
                           "required": ["numero"], "additionalProperties": False}}}

    def test_todas_as_ferramentas_reais_convertem(self):
        for spec in _ferramentas_do_usuario(_Usuario(papel="admin")):
            f = llm.ferramenta_para_openai(spec)["function"]
            assert f["name"] == spec["name"]
            assert f["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# Laço de tool-use no formato OpenAI (OpenRouter simulado)
# ---------------------------------------------------------------------------
class TestOpenRouterToolUse:
    def test_resposta_simples(self, monkeypatch, engine):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        chamadas = []

        def falso(url, headers, payload, timeout):
            chamadas.append((url, headers, payload))
            return _resp_http(200, _msg_openrouter("Olá!"))

        monkeypatch.setattr(llm, "_enviar_http", falso)
        with Session(engine) as s:
            r = responder("oi", [], s, _Usuario(), 1)
        assert r["resposta"] == "Olá!"
        url, headers, payload = chamadas[0]
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert headers["Authorization"] == f"Bearer {CHAVE_FALSA}"
        assert payload["model"] == "anthropic/claude-sonnet-4.5"
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][-1] == {"role": "user", "content": "oi"}
        assert payload["tools"][0]["type"] == "function"
        # histórico neutro, serializável em JSON, sem blocos do provedor
        json.dumps(r["historico"])
        assert r["historico"][-1] == {"role": "assistant", "content": "Olá!"}

    def test_laco_de_ferramenta_executa_e_devolve_resultado(self, monkeypatch, engine):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        payloads = []
        respostas = iter([
            _msg_openrouter(None, [_tool_call("buscar_animal", {"numero": "500"})], "tool_calls"),
            _msg_openrouter("O animal 500 é a Estrela."),
        ])

        def falso(url, headers, payload, timeout):
            payloads.append(json.loads(json.dumps(payload)))
            return _resp_http(200, next(respostas))

        monkeypatch.setattr(llm, "_enviar_http", falso)
        with Session(engine) as s:
            r = responder("quem é o 500?", [], s, _Usuario(), 1)
        assert r["resposta"] == "O animal 500 é a Estrela."
        segunda = payloads[1]["messages"]
        assert segunda[-2]["role"] == "assistant" and segunda[-2]["tool_calls"][0]["function"]["name"] == "buscar_animal"
        assert segunda[-2]["tool_calls"][0]["function"]["arguments"] == '{"numero": "500"}'
        tool = segunda[-1]
        assert tool["role"] == "tool" and tool["tool_call_id"] == "call_1"
        assert "Estrela" in tool["content"]

    def test_historico_devolvido_e_aceito_na_proxima_pergunta(self, monkeypatch, engine):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        respostas = iter([
            _msg_openrouter(None, [_tool_call("buscar_animal", {"numero": "500"})], "tool_calls"),
            _msg_openrouter("é a Estrela"),
            _msg_openrouter("de nada"),
        ])
        payloads = []

        def falso(url, headers, payload, timeout):
            payloads.append(json.loads(json.dumps(payload)))
            return _resp_http(200, next(respostas))

        monkeypatch.setattr(llm, "_enviar_http", falso)
        with Session(engine) as s:
            r1 = responder("quem é o 500?", [], s, _Usuario(), 1)
            r2 = responder("obrigado", json.loads(json.dumps(r1["historico"])), s, _Usuario(), 1)
        assert r2["resposta"] == "de nada"
        roles = [m["role"] for m in payloads[2]["messages"]]
        assert roles == ["system", "user", "assistant", "tool", "assistant", "user"]

    def test_ferramenta_sem_permissao_nao_e_oferecida_nem_executada(self, monkeypatch, engine):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        payloads = []
        respostas = iter([
            _msg_openrouter(None, [_tool_call("consultar_financeiro", {})], "tool_calls"),
            _msg_openrouter("sem permissão"),
        ])

        def falso(url, headers, payload, timeout):
            payloads.append(json.loads(json.dumps(payload)))
            return _resp_http(200, next(respostas))

        monkeypatch.setattr(llm, "_enviar_http", falso)
        usuario = _Usuario(papel="operador", permissoes="rebanho")
        with Session(engine) as s:
            responder("quanto devo?", [], s, usuario, 1)
        oferecidas = {t["function"]["name"] for t in payloads[0]["tools"]}
        assert "consultar_financeiro" not in oferecidas and "buscar_animal" in oferecidas
        assert "permissão" in payloads[1]["messages"][-1]["content"]

    def test_usuario_sem_nenhum_modulo_nao_manda_tools(self, monkeypatch, engine):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        payloads = []

        def falso(url, headers, payload, timeout):
            payloads.append(payload)
            return _resp_http(200, _msg_openrouter("ok"))

        monkeypatch.setattr(llm, "_enviar_http", falso)
        with Session(engine) as s:
            responder("oi", [], s, _Usuario(papel="operador", permissoes=""), 1)
        assert "tools" not in payloads[0]

    def test_argumentos_invalidos_do_modelo_nao_derrubam(self, monkeypatch, engine):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        respostas = iter([
            _msg_openrouter(None, [{"id": "c1", "type": "function", "function": {"name": "listar_lotes", "arguments": "{quebrado"}}], "tool_calls"),
            _msg_openrouter("feito"),
        ])
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(200, next(respostas)))
        with Session(engine) as s:
            assert responder("lotes", [], s, _Usuario(), 1)["resposta"] == "feito"

    def test_limite_de_rodadas(self, monkeypatch, engine):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setattr(
            llm, "_enviar_http",
            lambda *a, **k: _resp_http(200, _msg_openrouter(None, [_tool_call("listar_lotes", {})], "tool_calls")),
        )
        with Session(engine) as s:
            r = responder("lotes", [], s, _Usuario(), 1)
        assert "limite de consultas" in r["resposta"]

    def test_ensinamento_entra_no_system(self, monkeypatch, engine):
        from fazenda.models import AssistenteEnsinamento
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        capturado = {}

        def falso(url, headers, payload, timeout):
            capturado.update(payload)
            return _resp_http(200, _msg_openrouter("ok"))

        monkeypatch.setattr(llm, "_enviar_http", falso)
        with Session(engine) as s:
            s.add(AssistenteEnsinamento(fazenda_id=1, usuario_id=1, titulo="Regra", texto="Lote 4 é de secas."))
            s.add(AssistenteEnsinamento(fazenda_id=2, usuario_id=1, titulo="Outra", texto="NAO VAZAR"))
            s.commit()
            responder("oi", [], s, _Usuario(), 1)
        sistema = capturado["messages"][0]["content"]
        assert "Regra: Lote 4 é de secas." in sistema and "NAO VAZAR" not in sistema


# ---------------------------------------------------------------------------
# Histórico antigo / inválido é descartado, nunca 500
# ---------------------------------------------------------------------------
class TestHistoricoIncompativel:
    HISTORICO_ANTHROPIC_ANTIGO = [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": [{"type": "text", "text": "Olá"}]},
        {"role": "user", "content": "e o estoque?"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "consultar_estoque", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": "{}"}]}]},
    ]

    def test_validador(self):
        assert llm.historico_compativel(self.HISTORICO_ANTHROPIC_ANTIGO) is False
        assert llm.historico_compativel([]) is True
        assert llm.historico_compativel([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]) is True
        assert llm.historico_compativel([{"role": "assistant", "content": "b"}]) is False
        assert llm.historico_compativel([{"role": "xpto", "content": "b"}]) is False
        assert llm.historico_compativel(["lixo"]) is False
        # tool_call sem resposta correspondente
        assert llm.historico_compativel([
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "x", "name": "listar_lotes", "arguments": {}}]},
            {"role": "user", "content": "b"},
        ]) is False

    def test_historico_antigo_e_descartado_sem_erro(self, monkeypatch, engine):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        payloads = []

        def falso(url, headers, payload, timeout):
            payloads.append(payload)
            return _resp_http(200, _msg_openrouter("ok"))

        monkeypatch.setattr(llm, "_enviar_http", falso)
        with Session(engine) as s:
            r = responder("nova pergunta", self.HISTORICO_ANTHROPIC_ANTIGO, s, _Usuario(), 1)
        assert r["resposta"] == "ok"
        assert [m["role"] for m in payloads[0]["messages"]] == ["system", "user"]

    def test_historico_antigo_via_endpoint_nao_da_500(self, client, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(200, _msg_openrouter("ok")))
        r = client.post("/assistente/perguntar", json={"mensagem": "oi", "historico": self.HISTORICO_ANTHROPIC_ANTIGO})
        assert r.status_code == 200, r.text
        assert r.json()["resposta"] == "ok"


# ---------------------------------------------------------------------------
# Erros do provedor -> 503 com mensagem clara
# ---------------------------------------------------------------------------
MSG_USUARIO = "O assistente está temporariamente indisponível. Tente novamente em instantes."


class TestErrosOpenRouter:
    @pytest.mark.parametrize("status,corpo,tipo,dica", [
        (402, {"error": {"message": "Insufficient credits", "code": 402}}, "saldo", "saldo"),
        (401, {"error": {"message": "No auth credentials found", "code": 401}}, "chave", "chave"),
        (403, {"error": {"message": "forbidden", "code": 403}}, "chave", "chave"),
        (429, {"error": {"message": "Rate limit", "code": 429}}, "limite", "limite"),
        (404, {"error": {"message": "No endpoints found for foo/bar", "code": 404}}, "modelo", "ASSISTENTE_MODELO"),
        (400, {"error": {"message": "foo/bar is not a valid model ID", "code": 400}}, "modelo", "ASSISTENTE_MODELO"),
        (500, {"error": {"message": "boom"}}, "indisponivel", "provedor"),
        (503, {"error": {"message": "overloaded"}}, "indisponivel", "provedor"),
    ])
    def test_status_http(self, client, monkeypatch, status, corpo, tipo, dica):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(status, corpo))
        r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        detalhe = r.json()["detail"]
        assert detalhe.startswith(MSG_USUARIO)
        assert dica.lower() in detalhe.lower()  # admin ganha a dica técnica
        assert CHAVE_FALSA not in detalhe
        assert llm.status_assistente()["ultimo_erro"]["tipo"] == tipo

    def test_usuario_comum_ve_so_a_mensagem_generica(self, client, monkeypatch):
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _Usuario(papel="operador", permissoes="rebanho")
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(402, {"error": {"message": "Insufficient credits"}}))
        r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        assert r.json()["detail"] == MSG_USUARIO

    def test_usuario_comum_sem_configuracao_ve_so_a_generica(self, client):
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _Usuario(papel="operador", permissoes="rebanho")
        r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        assert r.json()["detail"] == MSG_USUARIO

    def test_erro_dentro_de_200(self, client, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        corpo = {"error": {"message": "Provider returned error", "code": 502}}
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(200, corpo))
        r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        assert llm.status_assistente()["ultimo_erro"]["tipo"] == "indisponivel"

    def test_timeout(self, client, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)

        def estoura(*a, **k):
            raise httpx.ReadTimeout("lento")

        monkeypatch.setattr(llm, "_enviar_http", estoura)
        r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        assert r.json()["detail"].startswith(MSG_USUARIO) and "demorou" in r.json()["detail"]
        assert llm.status_assistente()["ultimo_erro"]["tipo"] == "timeout"

    def test_rede(self, client, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)

        def cai(*a, **k):
            raise httpx.ConnectError("dns")

        monkeypatch.setattr(llm, "_enviar_http", cai)
        r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        assert llm.status_assistente()["ultimo_erro"]["tipo"] == "rede"

    def test_resposta_que_nao_e_json(self, client, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(200, texto="<html>oops</html>"))
        r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        assert llm.status_assistente()["ultimo_erro"]["tipo"] == "resposta_invalida"

    def test_sem_chave_no_endpoint(self, client):
        r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        assert "OPENROUTER_API_KEY" in r.json()["detail"]
        assert llm.status_assistente()["ultimo_erro"]["tipo"] == "configuracao"

    def test_log_nao_vaza_chave(self, client, monkeypatch, caplog):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        corpo = {"error": {"message": f"Invalid key {CHAVE_FALSA} Bearer {CHAVE_FALSA}"}}
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(401, corpo))
        with caplog.at_level("DEBUG"):
            r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        assert r.status_code == 503
        assert CHAVE_FALSA not in caplog.text
        assert CHAVE_FALSA not in r.text
        assert CHAVE_FALSA not in json.dumps(llm.status_assistente())
        assert "tipo=chave" in caplog.text

    def test_sucesso_limpa_nada_mas_registra_ultimo_sucesso(self, client, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(200, _msg_openrouter("ok")))
        assert client.post("/assistente/perguntar", json={"mensagem": "oi"}).status_code == 200
        assert llm.status_assistente()["ultimo_sucesso_em"]


class TestErrosAnthropic:
    def _com_excecao(self, monkeypatch, excecao):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        patcher = patch("anthropic.Anthropic")
        mock = patcher.start()
        mock.return_value.messages.create.side_effect = excecao
        return patcher

    def _status_exc(self, status, msg):
        import anthropic
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        resp = httpx.Response(status, request=req, json={"error": {"message": msg}})
        return anthropic.APIStatusError(msg, response=resp, body={"error": {"message": msg}})

    @pytest.mark.parametrize("status,msg,tipo", [
        (400, "Your credit balance is too low to access the Anthropic API.", "saldo"),
        (401, "invalid x-api-key", "chave"),
        (429, "rate limited", "limite"),
        (404, "model: claude-xyz", "modelo"),
        (529, "Overloaded", "indisponivel"),
        (500, "internal", "indisponivel"),
    ])
    def test_status(self, client, monkeypatch, status, msg, tipo):
        p = self._com_excecao(monkeypatch, self._status_exc(status, msg))
        try:
            r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        finally:
            p.stop()
        assert r.status_code == 503
        assert r.json()["detail"].startswith(MSG_USUARIO)
        assert llm.status_assistente()["ultimo_erro"]["tipo"] == tipo

    def test_timeout_e_rede(self, client, monkeypatch):
        import anthropic
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        p = self._com_excecao(monkeypatch, anthropic.APITimeoutError(request=req))
        try:
            r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        finally:
            p.stop()
        assert r.status_code == 503 and llm.status_assistente()["ultimo_erro"]["tipo"] == "timeout"
        p = self._com_excecao(monkeypatch, anthropic.APIConnectionError(request=req))
        try:
            r = client.post("/assistente/perguntar", json={"mensagem": "oi"})
        finally:
            p.stop()
        assert r.status_code == 503 and llm.status_assistente()["ultimo_erro"]["tipo"] == "rede"

    def test_laco_de_tool_use_com_historico_neutro(self, monkeypatch, engine):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        bloco_uso = MagicMock(type="tool_use", id="toolu_1", input={"numero": "500"})
        bloco_uso.name = "buscar_animal"
        bloco_texto = MagicMock(type="text", text="Achei!")
        r1 = MagicMock(content=[bloco_uso], stop_reason="tool_use")
        r2 = MagicMock(content=[bloco_texto], stop_reason="end_turn")
        with patch("anthropic.Anthropic") as M:
            M.return_value.messages.create.side_effect = [r1, r2]
            with Session(engine) as s:
                r = responder("quem é 500?", [], s, _Usuario(), 1)
            segunda = M.return_value.messages.create.call_args_list[1].kwargs["messages"]
        assert r["resposta"] == "Achei!"
        assert segunda[1]["content"][0]["type"] == "tool_use"
        assert segunda[2]["content"][0]["type"] == "tool_result"
        assert segunda[2]["content"][0]["tool_use_id"] == "toolu_1"
        assert all(m["role"] in ("user", "assistant", "tool") for m in r["historico"])
        json.dumps(r["historico"])


# ---------------------------------------------------------------------------
# GET /assistente/status (admin)
# ---------------------------------------------------------------------------
class TestStatusEndpoint:
    def test_admin_ve_status_sem_segredo(self, client, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        r = client.get("/assistente/status")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["provedor"] == "openrouter" and corpo["configurado"] is True
        assert corpo["modelo"] == "anthropic/claude-sonnet-4.5"
        assert corpo["ultimo_erro"] is None
        assert CHAVE_FALSA not in r.text

    def test_status_mostra_ultimo_erro(self, client, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
        monkeypatch.setattr(llm, "_enviar_http", lambda *a, **k: _resp_http(402, {"error": {"message": "x"}}))
        client.post("/assistente/perguntar", json={"mensagem": "oi"})
        corpo = client.get("/assistente/status").json()
        assert corpo["ultimo_erro"]["tipo"] == "saldo" and corpo["ultimo_erro"]["em"]

    def test_nao_admin_leva_403(self, client):
        import main
        from fazenda.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: _Usuario(papel="operador", permissoes="rebanho")
        assert client.get("/assistente/status").status_code == 403
