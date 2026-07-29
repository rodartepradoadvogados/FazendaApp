"""
Testes do cliente do Firebase Cloud Messaging — fazenda/rules/fcm.py.
Nunca bate na rede real: mocka httpx.post e google.oauth2.service_account
(o access token OAuth2 nunca é gerado de verdade nestes testes).
"""
from __future__ import annotations

import base64
import json

import httpx
import pytest

import fazenda.rules.fcm as fcm_module
from fazenda.config import settings

_SERVICE_ACCOUNT_FAKE = {
    "type": "service_account",
    "project_id": "cowdata-fazenda-teste",
    "private_key_id": "abc123",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk@cowdata-fazenda-teste.iam.gserviceaccount.com",
    "client_id": "123",
}


class _RespostaFalsa:
    def __init__(self, status_code: int, corpo: dict | None = None):
        self.status_code = status_code
        self._corpo = corpo or {}
        self.text = json.dumps(self._corpo)

    def json(self):
        return self._corpo


@pytest.fixture(autouse=True)
def _limpar_cache_credenciais(monkeypatch):
    # _credenciais_cache é memoizado a nível de módulo — evita um teste
    # contaminar o próximo com credenciais de uma fixture anterior.
    monkeypatch.setattr(fcm_module, "_credenciais_cache", None)


def test_habilitado_false_sem_configuracao(monkeypatch):
    monkeypatch.setattr(settings, "fcm_service_account_json", "")
    assert fcm_module.habilitado() is False


def test_habilitado_true_com_configuracao(monkeypatch):
    monkeypatch.setattr(settings, "fcm_service_account_json", json.dumps(_SERVICE_ACCOUNT_FAKE))
    assert fcm_module.habilitado() is True


def test_json_invalido_nao_explode_ao_checar_habilitado(monkeypatch):
    monkeypatch.setattr(settings, "fcm_service_account_json", "isso não é json")
    # habilitado() só olha se a env está preenchida — não valida o conteúdo.
    assert fcm_module.habilitado() is True


def test_carregar_json_aceita_json_direto(monkeypatch):
    monkeypatch.setattr(settings, "fcm_service_account_json", json.dumps(_SERVICE_ACCOUNT_FAKE))
    dados = fcm_module._carregar_json_conta_servico()
    assert dados["project_id"] == "cowdata-fazenda-teste"


def test_carregar_json_aceita_base64(monkeypatch):
    b64 = base64.b64encode(json.dumps(_SERVICE_ACCOUNT_FAKE).encode()).decode()
    monkeypatch.setattr(settings, "fcm_service_account_json", b64)
    dados = fcm_module._carregar_json_conta_servico()
    assert dados["project_id"] == "cowdata-fazenda-teste"


def test_carregar_json_totalmente_invalido_lanca_runtimeerror(monkeypatch):
    monkeypatch.setattr(settings, "fcm_service_account_json", "nem json nem base64 valido !!!")
    with pytest.raises(RuntimeError):
        fcm_module._carregar_json_conta_servico()


def test_project_id_usa_o_do_json_quando_nao_configurado_explicitamente(monkeypatch):
    monkeypatch.setattr(settings, "fcm_service_account_json", json.dumps(_SERVICE_ACCOUNT_FAKE))
    monkeypatch.setattr(settings, "fcm_project_id", "")
    assert fcm_module.project_id() == "cowdata-fazenda-teste"


def test_project_id_prioriza_config_explicita(monkeypatch):
    monkeypatch.setattr(settings, "fcm_service_account_json", json.dumps(_SERVICE_ACCOUNT_FAKE))
    monkeypatch.setattr(settings, "fcm_project_id", "outro-projeto")
    assert fcm_module.project_id() == "outro-projeto"


class TestEnviar:
    @pytest.fixture(autouse=True)
    def _configurar(self, monkeypatch):
        monkeypatch.setattr(settings, "fcm_service_account_json", json.dumps(_SERVICE_ACCOUNT_FAKE))
        monkeypatch.setattr(settings, "fcm_project_id", "cowdata-fazenda-teste")
        monkeypatch.setattr(fcm_module, "_access_token", lambda: "token-fake-de-teste")

    def test_monta_payload_correto_e_envia(self, monkeypatch):
        chamadas = []

        def _post_fake(url, headers=None, json=None, timeout=None):
            chamadas.append({"url": url, "headers": headers, "json": json})
            return _RespostaFalsa(200)

        monkeypatch.setattr(httpx, "post", _post_fake)
        fcm_module.enviar("tok-1", "Agenda do dia", "Você tem 3 atividades", "/agenda", count=3)

        assert len(chamadas) == 1
        c = chamadas[0]
        assert c["url"] == "https://fcm.googleapis.com/v1/projects/cowdata-fazenda-teste/messages:send"
        assert c["headers"]["Authorization"] == "Bearer token-fake-de-teste"
        msg = c["json"]["message"]
        assert msg["token"] == "tok-1"
        assert msg["notification"] == {"title": "Agenda do dia", "body": "Você tem 3 atividades"}
        # "data" do FCM só aceita string — count precisa virar string.
        assert msg["data"]["count"] == "3"
        assert isinstance(msg["data"]["count"], str)
        assert msg["data"]["url"] == "/agenda"
        assert msg["android"]["priority"] == "HIGH"
        assert msg["android"]["notification"]["color"] == "#3A0F1A"

    def test_sem_count_nao_inclui_a_chave(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(httpx, "post", lambda *a, **k: chamadas.append(k) or _RespostaFalsa(200))
        fcm_module.enviar("tok-1", "Título", "Corpo", "/financeiro")
        assert "count" not in chamadas[0]["json"]["message"]["data"]
        assert "notification_count" not in chamadas[0]["json"]["message"]["android"]["notification"]

    @pytest.mark.parametrize("status_erro", ["UNREGISTERED", "SENDER_ID_MISMATCH"])
    def test_token_morto_lanca_fcmtokeninvalido(self, monkeypatch, status_erro):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespostaFalsa(400, {"error": {"status": status_erro}}))
        with pytest.raises(fcm_module.FcmTokenInvalido):
            fcm_module.enviar("tok-morto", "Título", "Corpo", "/agenda")

    def test_404_lanca_fcmtokeninvalido_mesmo_sem_status_no_corpo(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespostaFalsa(404, {}))
        with pytest.raises(fcm_module.FcmTokenInvalido):
            fcm_module.enviar("tok-inexistente", "Título", "Corpo", "/agenda")

    def test_erro_de_configuracao_lanca_runtimeerror_generico(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespostaFalsa(403, {"error": {"status": "SERVICE_DISABLED"}}))
        with pytest.raises(RuntimeError):
            fcm_module.enviar("tok-1", "Título", "Corpo", "/agenda")

    def test_5xx_lanca_erro_para_o_chamador_tentar_de_novo_depois(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespostaFalsa(500, {}))
        with pytest.raises(RuntimeError):
            fcm_module.enviar("tok-1", "Título", "Corpo", "/agenda")

    def test_sucesso_nao_lanca_nada(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespostaFalsa(200, {"name": "projects/x/messages/1"}))
        fcm_module.enviar("tok-1", "Título", "Corpo", "/agenda")  # não deve lançar


def test_enviar_sem_configuracao_lanca_runtimeerror_claro(monkeypatch):
    monkeypatch.setattr(settings, "fcm_service_account_json", "")
    with pytest.raises(RuntimeError, match="não configurado"):
        fcm_module.enviar("tok-1", "Título", "Corpo", "/agenda")
