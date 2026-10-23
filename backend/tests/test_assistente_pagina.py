"""
Ferramentas de TELA do Assistente (`pagina_*`) — ver
fazenda/rules/ferramentas_pagina.py.

A regra central que estes testes travam: o backend NUNCA executa uma
ferramenta de tela. Ele devolve a chamada em `aguardando`, o navegador do
usuário executa e manda de volta em `resultados_pagina`. É o que evita
Chromium no servidor e o vazamento de sessão entre usuários.
"""
from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import ContratoFazenda, Fazenda
from fazenda.rules import assistente_llm as llm
from fazenda.rules import ferramentas_pagina as pagina
from fazenda.rules.assistente import responder

CHAVE_FALSA = "sk-or-...7890"


class _Usuario:
    def __init__(self, papel="admin", permissoes="indicadores,rebanho,financeiro,agenda"):
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
        # trava de tenant do main.py exige contrato ativo quando há fazenda
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.commit()
    return eng


def _resp_http(status=200, corpo=None):
    return httpx.Response(status, json=corpo if corpo is not None else {},
                          request=httpx.Request("POST", llm.URL_OPENROUTER))


def _msg(content=None, tool_calls=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"choices": [{"message": msg, "finish_reason": finish}]}


def _tool(nome, args, id_="call_1"):
    return {"id": id_, "type": "function", "function": {"name": nome, "arguments": json.dumps(args)}}


def _openrouter(monkeypatch, respostas):
    monkeypatch.setenv("OPENROUTER_API_KEY", CHAVE_FALSA)
    it = iter(respostas)
    enviados: list[dict] = []

    def falso(url, headers, payload, timeout):
        enviados.append(json.loads(json.dumps(payload)))
        return _resp_http(200, next(it))

    monkeypatch.setattr(llm, "_enviar_http", falso)
    return enviados


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------
class TestCaminhoSeguro:
    @pytest.mark.parametrize("caminho", ["/alimentacao/dietas", "/lancamentos", "/app/menu?x=1"])
    def test_aceita_caminho_interno(self, caminho):
        assert pagina.caminho_seguro(caminho) == caminho

    @pytest.mark.parametrize("caminho", [
        "https://evil.com/x",      # URL absoluta
        "//evil.com/x",            # protocol-relative
        "javascript:alert(1)",     # esquema
        "relativo/sem-barra",      # não é caminho do app
        "/a\\b",                   # escape estranho
        "/tem espaço",
        123,
        None,
    ])
    def test_recusa_o_que_sairia_do_app(self, caminho):
        assert pagina.caminho_seguro(caminho) is None

    def test_validar_recusa_caminho_externo_com_erro_claro(self):
        with pytest.raises(ValueError) as e:
            pagina.validar("pagina_navegar", {"caminho": "https://evil.com"})
        assert "interno" in str(e.value)

    def test_validar_normaliza_ler_com_padroes(self):
        assert pagina.validar("pagina_ler", {}) == {"seletor": "main", "limite": 4000}

    def test_validar_recusa_limite_absurdo(self):
        with pytest.raises(ValueError):
            pagina.validar("pagina_ler", {"seletor": "main", "limite": 999999})


# ---------------------------------------------------------------------------
# Protocolo com o navegador
# ---------------------------------------------------------------------------
class TestProtocolo:
    def test_ferramenta_de_tela_nao_e_executada_no_servidor(self, monkeypatch, engine):
        enviados = _openrouter(monkeypatch, [
            _msg(None, [_tool("pagina_navegar", {"caminho": "/alimentacao/dietas"})], "tool_calls"),
        ])
        with Session(engine) as s:
            r = responder("abre as dietas", [], s, _Usuario(), 1)
        assert r["aguardando"] == [{
            "id": "call_1", "nome": "pagina_navegar", "argumentos": {"caminho": "/alimentacao/dietas"},
        }]
        assert r["resposta"] == ""
        # o histórico termina com a chamada pendente, para o front devolver o resultado
        assert r["historico"][-1]["tool_calls"][0]["name"] == "pagina_navegar"
        assert len(enviados) == 1  # uma única ida ao modelo; nada de executar aqui

    def test_resultado_do_navegador_continua_a_conversa(self, monkeypatch, engine):
        enviados = _openrouter(monkeypatch, [
            _msg(None, [_tool("pagina_ler", {"seletor": "main"})], "tool_calls"),
            _msg("A tela mostra 12 dietas cadastradas."),
        ])
        with Session(engine) as s:
            primeiro = responder("o que tem na tela?", [], s, _Usuario(), 1)
            segundo = responder(
                "", primeiro["historico"], s, _Usuario(), 1,
                resultados_pagina=[{"id": "call_1", "resultado": {"ok": True, "texto": "Dietas (12)"}}],
            )
        assert segundo["resposta"] == "A tela mostra 12 dietas cadastradas."
        tool_msg = enviados[1]["messages"][-1]
        assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_1"
        assert "Dietas (12)" in tool_msg["content"]

    def test_cliente_nao_pode_forjar_resultado_de_ferramenta_de_dados(self, monkeypatch, engine):
        # Sem nenhuma chamada de tela pendente, `resultados_pagina` é ignorado.
        _openrouter(monkeypatch, [_msg("nada a fazer")])
        with Session(engine) as s:
            r = responder(
                "oi", [], s, _Usuario(), 1,
                resultados_pagina=[{"id": "call_x", "resultado": {"ok": True, "texto": "invadido"}}],
            )
        assert r["resposta"] == "nada a fazer"

    def test_resultado_faltando_nao_deixa_conversa_pendurada(self, monkeypatch, engine):
        _openrouter(monkeypatch, [
            _msg(None, [_tool("pagina_info", {})], "tool_calls"),
        ])
        with Session(engine) as s:
            primeiro = responder("onde estou?", [], s, _Usuario(), 1)
            segundo = responder("", primeiro["historico"], s, _Usuario(), 1, resultados_pagina=[])
        assert "não devolveu" in segundo["resposta"]
        assert segundo["historico"] == []

    def test_argumento_invalido_vira_erro_de_ferramenta_e_nao_trava(self, monkeypatch, engine):
        _openrouter(monkeypatch, [
            _msg(None, [_tool("pagina_navegar", {"caminho": "https://evil.com"})], "tool_calls"),
            _msg("Não posso sair do app."),
        ])
        with Session(engine) as s:
            r = responder("vai pro google", [], s, _Usuario(), 1)
        assert r["resposta"] == "Não posso sair do app."
        erro = json.loads(r["historico"][-2]["content"])
        assert "interno" in erro["erro"]

    def test_ferramentas_de_tela_entram_na_lista_oferecida(self):
        nomes = {s["name"] for s in pagina.especificacoes()}
        assert nomes == set(pagina.NOMES)
        assert "pagina_navegar" in nomes


# ---------------------------------------------------------------------------
# Contrato do endpoint (o front depende dele para saber o que executar)
# ---------------------------------------------------------------------------
class TestEndpoint:
    @pytest.fixture
    def client(self, monkeypatch, engine):
        import main
        import fazenda.database as database
        from fazenda.auth import get_current_user, get_fazenda_atual_id

        monkeypatch.setattr(database, "engine", engine)

        def _sess():
            with Session(engine) as s:
                yield s

        main.app.dependency_overrides[database.get_session] = _sess
        main.app.dependency_overrides[get_current_user] = lambda: _Usuario()
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
        from fastapi.testclient import TestClient
        with TestClient(main.app) as c:
            yield c
        main.app.dependency_overrides.clear()

    def test_devolve_aguardando_para_o_front_executar(self, client, monkeypatch):
        _openrouter(monkeypatch, [
            _msg(None, [_tool("pagina_info", {})], "tool_calls"),
        ])
        r = client.post("/assistente/perguntar", json={"mensagem": "onde estou?"})
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["aguardando"][0]["nome"] == "pagina_info"
        assert corpo["aguardando"][0]["id"] == "call_1"

    def test_aceita_continuacao_sem_mensagem(self, client, monkeypatch):
        _openrouter(monkeypatch, [
            _msg(None, [_tool("pagina_info", {})], "tool_calls"),
            _msg("Você está em /lancamentos."),
        ])
        primeiro = client.post("/assistente/perguntar", json={"mensagem": "onde estou?"}).json()
        segundo = client.post("/assistente/perguntar", json={
            "historico": primeiro["historico"],
            "resultados_pagina": [{"id": "call_1", "resultado": {"ok": True, "caminho": "/lancamentos"}}],
        })
        assert segundo.status_code == 200
        assert segundo.json()["resposta"] == "Você está em /lancamentos."

    def test_mensagem_vazia_sem_resultado_e_400(self, client):
        assert client.post("/assistente/perguntar", json={"mensagem": "  "}).status_code == 400

    def test_resultados_demais_e_400(self, client):
        r = client.post("/assistente/perguntar", json={
            "mensagem": "oi", "resultados_pagina": [{"id": str(i), "resultado": "x"} for i in range(13)],
        })
        assert r.status_code == 400
