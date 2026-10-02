"""
Motor de LLM do Assistente — abstrai o provedor (OpenRouter ou Anthropic) e
traduz as falhas dele em mensagens claras.

Variáveis de ambiente (nomes exatos):
  ASSISTENTE_PROVEDOR   'openrouter' | 'anthropic'. Ausente: openrouter quando
                        OPENROUTER_API_KEY existe, senão anthropic quando
                        ANTHROPIC_API_KEY existe, senão erro de configuração.
  OPENROUTER_API_KEY    chave do OpenRouter (API compatível com OpenAI).
  ANTHROPIC_API_KEY     chave da Anthropic.
  ASSISTENTE_MODELOS_RESERVA  (opcional) modelos do OpenRouter, separados por vírgula, usados
                        quando o principal está sobrecarregado/indisponível.
  ASSISTENTE_MODELO     modelo. Padrão: 'anthropic/claude-sonnet-4.5'
                        (openrouter) ou 'claude-sonnet-5' (anthropic).

Histórico NEUTRO de provedor (é o que o front guarda e reenvia):
  {"role": "user", "content": "texto"}
  {"role": "assistant", "content": "texto" | None,
   "tool_calls": [{"id": "...", "name": "...", "arguments": {...}}]}
  {"role": "tool", "tool_call_id": "...", "name": "...", "content": "<json>"}
Cada provedor converte isso para o formato dele e a resposta de volta. Um
histórico em outro formato (o antigo, em blocos da Anthropic) é detectado por
`historico_compativel` e descartado — nunca vira erro 500.

Erros: toda falha do provedor vira `ErroAssistente` (RuntimeError) com um
`tipo` estável (configuracao, saldo, chave, limite, modelo, indisponivel,
timeout, rede, resposta_invalida, requisicao). O usuário comum vê só
"O assistente está temporariamente indisponível..."; o administrador recebe
também uma dica técnica curta. O detalhe vai para o log do servidor SEM
segredos (`_sem_segredos`).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

PROVEDOR_OPENROUTER = "openrouter"
PROVEDOR_ANTHROPIC = "anthropic"
PROVEDORES = (PROVEDOR_OPENROUTER, PROVEDOR_ANTHROPIC)
MODELO_PADRAO = {
    PROVEDOR_OPENROUTER: "anthropic/claude-sonnet-4.5",
    PROVEDOR_ANTHROPIC: "claude-sonnet-5",
}
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOKENS = 1536
TIMEOUT_SEGUNDOS = 90.0

MSG_INDISPONIVEL = "O assistente está temporariamente indisponível. Tente novamente em instantes."
_VARS_CHAVE = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")


class ErroAssistente(RuntimeError):
    """Falha do assistente com tipo estável. `str(e)` é a versão técnica
    (para administrador / logs); `mensagem(admin)` escolhe o texto certo."""

    def __init__(self, tipo: str, dica_admin: str, status: int | None = None):
        self.tipo = tipo
        self.dica_admin = dica_admin
        self.status = status
        super().__init__(f"{MSG_INDISPONIVEL} [Admin: {dica_admin}]")

    def mensagem(self, admin: bool) -> str:
        return str(self) if admin else MSG_INDISPONIVEL


# ---------------------------------------------------------------------------
# Segredos / log / status
# ---------------------------------------------------------------------------
def _sem_segredos(texto: str) -> str:
    """Remove do texto qualquer chave conhecida (valor das env vars de chave),
    tokens 'Bearer ...' e padrões sk-... antes de logar/guardar."""
    out = str(texto or "")
    for v in _VARS_CHAVE:
        valor = os.environ.get(v)
        if valor and len(valor) >= 6:
            out = out.replace(valor, "[chave]")
    out = re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer [chave]", out)
    out = re.sub(r"sk-[A-Za-z0-9_\-]{6,}", "sk-[chave]", out)
    return out


_lock = threading.Lock()
_estado: dict = {"ultimo_erro": None, "ultimo_sucesso_em": None}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resetar_estado_para_testes() -> None:
    with _lock:
        _estado["ultimo_erro"] = None
        _estado["ultimo_sucesso_em"] = None


def _registrar_erro(e: ErroAssistente, provedor: str | None, modelo: str | None, detalhe: str = "") -> None:
    with _lock:
        _estado["ultimo_erro"] = {"tipo": e.tipo, "em": _agora()}
    logger.warning(
        "assistente falhou provedor=%s modelo=%s tipo=%s status=%s detalhe=%s",
        provedor, modelo, e.tipo, e.status, _sem_segredos(detalhe)[:300],
    )


def _registrar_sucesso() -> None:
    with _lock:
        _estado["ultimo_sucesso_em"] = _agora()


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def _chave_do(provedor: str) -> str | None:
    var = "OPENROUTER_API_KEY" if provedor == PROVEDOR_OPENROUTER else "ANTHROPIC_API_KEY"
    return (os.environ.get(var) or "").strip() or None


def configuracao() -> dict:
    """Provedor/modelo efetivos e se estão utilizáveis — sem segredos."""
    explicito = (os.environ.get("ASSISTENTE_PROVEDOR") or "").strip().lower()
    motivo = None
    if explicito:
        provedor = explicito
        if provedor not in PROVEDORES:
            motivo = f"ASSISTENTE_PROVEDOR='{explicito}' inválido (use 'openrouter' ou 'anthropic')."
    elif _chave_do(PROVEDOR_OPENROUTER):
        provedor = PROVEDOR_OPENROUTER
    elif _chave_do(PROVEDOR_ANTHROPIC):
        provedor = PROVEDOR_ANTHROPIC
    else:
        provedor = None
        motivo = (
            "Assistente de IA não configurado: defina OPENROUTER_API_KEY (ou ANTHROPIC_API_KEY) "
            "nas variáveis do serviço (Railway > Variables)."
        )
    modelo = None
    if provedor in PROVEDORES:
        modelo = (os.environ.get("ASSISTENTE_MODELO") or "").strip() or MODELO_PADRAO[provedor]
        if not _chave_do(provedor):
            var = "OPENROUTER_API_KEY" if provedor == PROVEDOR_OPENROUTER else "ANTHROPIC_API_KEY"
            motivo = f"Provedor '{provedor}' selecionado, mas falta a variável {var} nas variáveis do serviço (Railway > Variables)."
    return {"provedor": provedor, "modelo": modelo, "configurado": motivo is None, "motivo": motivo}


def status_assistente() -> dict:
    cfg = configuracao()
    with _lock:
        return {
            "provedor": cfg["provedor"],
            "modelo": cfg["modelo"],
            "configurado": cfg["configurado"],
            "motivo": cfg["motivo"],
            "ultimo_erro": dict(_estado["ultimo_erro"]) if _estado["ultimo_erro"] else None,
            "ultimo_sucesso_em": _estado["ultimo_sucesso_em"],
        }


# ---------------------------------------------------------------------------
# Histórico neutro
# ---------------------------------------------------------------------------
def historico_compativel(historico) -> bool:
    """True se `historico` está no formato neutro e é consistente (cada
    tool_call respondido por uma mensagem 'tool', começando por 'user')."""
    if not isinstance(historico, list):
        return False
    if not historico:
        return True
    pendentes: set[str] = set()
    for i, m in enumerate(historico):
        if not isinstance(m, dict):
            return False
        papel = m.get("role")
        conteudo = m.get("content")
        if i == 0 and papel != "user":
            return False
        if papel == "user":
            if pendentes or not isinstance(conteudo, str):
                return False
        elif papel == "assistant":
            if pendentes:
                return False
            if conteudo is not None and not isinstance(conteudo, str):
                return False
            chamadas = m.get("tool_calls")
            if chamadas is not None:
                if not isinstance(chamadas, list):
                    return False
                for c in chamadas:
                    if not (isinstance(c, dict) and isinstance(c.get("id"), str)
                            and isinstance(c.get("name"), str) and isinstance(c.get("arguments"), dict)):
                        return False
                    pendentes.add(c["id"])
            elif conteudo is None:
                return False
        elif papel == "tool":
            if not isinstance(conteudo, str) or m.get("tool_call_id") not in pendentes:
                return False
            pendentes.discard(m["tool_call_id"])
        else:
            return False
    return not pendentes


def limpar_historico(historico) -> list[dict]:
    """Histórico utilizável: o próprio, se compatível; senão lista vazia."""
    if historico_compativel(historico):
        return list(historico)
    logger.info("assistente: histórico incompatível/antigo descartado")
    return []


# ---------------------------------------------------------------------------
# Conversão de ferramentas
# ---------------------------------------------------------------------------
def ferramenta_para_openai(spec: dict) -> dict:
    """Schema da Anthropic (input_schema) -> function calling da OpenAI."""
    return {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec.get("description", ""),
            "parameters": spec.get("input_schema") or {"type": "object", "properties": {}},
        },
    }


# ---------------------------------------------------------------------------
# Classificação de erros
# ---------------------------------------------------------------------------
def _erro(tipo: str, status: int | None = None, **fmt) -> ErroAssistente:
    dicas = {
        "saldo": "saldo/limite de crédito do provedor de IA esgotado — verifique o saldo/limite da chave no provedor.",
        "chave": "chave do provedor de IA inválida ou sem permissão — confira OPENROUTER_API_KEY / ANTHROPIC_API_KEY.",
        "limite": "o provedor de IA limitou a taxa de requisições (429) — aguarde ou aumente o limite.",
        "modelo": "modelo '{modelo}' inexistente/indisponível no provedor — confira ASSISTENTE_MODELO.",
        "indisponivel": "provedor de IA fora do ar ou sobrecarregado (HTTP {status}) — tente de novo em instantes.",
        "timeout": "o provedor de IA demorou demais para responder (timeout).",
        "rede": "falha de rede ao falar com o provedor de IA.",
        "resposta_invalida": "o provedor de IA devolveu uma resposta que o sistema não entendeu.",
        "requisicao": "o provedor de IA recusou a requisição (HTTP {status}) — veja o log do servidor.",
    }
    return ErroAssistente(tipo, dicas[tipo].format(status=status, **fmt), status)


def classificar_http(status: int, corpo: str, modelo: str) -> ErroAssistente:
    """Mapeia (status HTTP, texto do corpo) de qualquer provedor num ErroAssistente."""
    txt = (corpo or "").lower()
    if status == 402 or "credit balance" in txt or "insufficient credit" in txt or "insufficient_quota" in txt \
            or "billing" in txt and status in (400, 403):
        return _erro("saldo", status)
    if status in (401, 403):
        return _erro("chave", status)
    if status == 429:
        return _erro("limite", status)
    if status == 404 or (status == 400 and "model" in txt and any(
            k in txt for k in ("not a valid", "invalid model", "not found", "does not exist", "unknown model", "no endpoints"))):
        return _erro("modelo", status, modelo=modelo)
    if status == 408:
        return _erro("timeout", status)
    if status >= 500:
        return _erro("indisponivel", status)
    return _erro("requisicao", status)


# ---------------------------------------------------------------------------
# OpenRouter (API compatível com OpenAI)
# ---------------------------------------------------------------------------
def _enviar_http(url: str, headers: dict, payload: dict, timeout: float) -> httpx.Response:
    """Único ponto de rede do OpenRouter (os testes trocam esta função)."""
    return httpx.post(url, headers=headers, json=payload, timeout=httpx.Timeout(timeout, connect=10.0))


def _mensagens_para_openai(system: str, mensagens: list[dict]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in mensagens:
        papel = m["role"]
        if papel == "user":
            out.append({"role": "user", "content": m["content"]})
        elif papel == "assistant":
            msg: dict = {"role": "assistant", "content": m.get("content")}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                    for c in m["tool_calls"]
                ]
            out.append(msg)
        elif papel == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
    return out


def _texto_do_erro(corpo) -> str:
    if isinstance(corpo, dict):
        err = corpo.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        if err:
            return str(err)
    return ""


def _completar_openrouter(system: str, mensagens: list[dict], ferramentas: list[dict], modelo: str) -> dict:
    chave = _chave_do(PROVEDOR_OPENROUTER)
    payload: dict = {
        "model": modelo,
        "max_tokens": MAX_TOKENS,
        "messages": _mensagens_para_openai(system, mensagens),
    }
    if ferramentas:
        payload["tools"] = [ferramenta_para_openai(f) for f in ferramentas]
    headers = {
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
        "X-Title": "CowData",
    }
    try:
        resp = _enviar_http(URL_OPENROUTER, headers, payload, TIMEOUT_SEGUNDOS)
    except httpx.TimeoutException as e:
        raise _com_detalhe(_erro("timeout"), e) from None
    except httpx.HTTPError as e:
        raise _com_detalhe(_erro("rede"), e) from None

    if resp.status_code >= 400:
        raise _com_detalhe(classificar_http(resp.status_code, resp.text, modelo), resp.text)
    try:
        dados = resp.json()
    except ValueError:
        raise _com_detalhe(_erro("resposta_invalida"), "corpo não é JSON") from None
    if not isinstance(dados, dict):
        raise _com_detalhe(_erro("resposta_invalida"), "JSON inesperado")
    # OpenRouter pode devolver HTTP 200 com {"error": {...}} (falha do provedor a jusante).
    if dados.get("error") and not dados.get("choices"):
        err = dados["error"]
        codigo = err.get("code") if isinstance(err, dict) else None
        status = codigo if isinstance(codigo, int) else 502
        raise _com_detalhe(classificar_http(status, _texto_do_erro(dados), modelo), _texto_do_erro(dados))
    try:
        escolha = dados["choices"][0]
        msg = escolha["message"]
    except (KeyError, IndexError, TypeError):
        raise _com_detalhe(_erro("resposta_invalida"), "sem choices[0].message") from None
    if isinstance(escolha, dict) and escolha.get("error") and not msg:
        raise _com_detalhe(_erro("indisponivel", 502), _texto_do_erro({"error": escolha["error"]}))

    chamadas = []
    for c in msg.get("tool_calls") or []:
        fn = (c or {}).get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        chamadas.append({"id": str(c.get("id") or f"call_{len(chamadas)}"), "name": str(fn.get("name") or ""), "arguments": args})
    conteudo = msg.get("content")
    if isinstance(conteudo, list):  # alguns provedores devolvem partes
        conteudo = "".join(p.get("text", "") for p in conteudo if isinstance(p, dict))
    out: dict = {"role": "assistant", "content": conteudo if isinstance(conteudo, str) and conteudo else None}
    if chamadas:
        out["tool_calls"] = chamadas
    elif out["content"] is None:
        out["content"] = ""
    return out


def _com_detalhe(e: ErroAssistente, detalhe) -> ErroAssistente:
    e._detalhe_log = str(detalhe)  # type: ignore[attr-defined]
    return e


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
def _mensagens_para_anthropic(mensagens: list[dict]) -> list[dict]:
    out: list[dict] = []

    def _acrescentar_user(blocos: list[dict]) -> None:
        # Anthropic exige alternância; junta tool_results + próximo texto do usuário.
        if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
            out[-1]["content"].extend(blocos)
        else:
            out.append({"role": "user", "content": blocos})

    for m in mensagens:
        papel = m["role"]
        if papel == "user":
            _acrescentar_user([{"type": "text", "text": m["content"]}])
        elif papel == "assistant":
            blocos: list[dict] = []
            if m.get("content"):
                blocos.append({"type": "text", "text": m["content"]})
            for c in m.get("tool_calls") or []:
                blocos.append({"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]})
            out.append({"role": "assistant", "content": blocos or [{"type": "text", "text": "(sem resposta)"}]})
        elif papel == "tool":
            _acrescentar_user([{
                "type": "tool_result", "tool_use_id": m["tool_call_id"],
                "content": [{"type": "text", "text": m["content"]}],
            }])
    return out


def _completar_anthropic(system: str, mensagens: list[dict], ferramentas: list[dict], modelo: str) -> dict:
    import anthropic

    cliente = anthropic.Anthropic(api_key=_chave_do(PROVEDOR_ANTHROPIC), timeout=TIMEOUT_SEGUNDOS, max_retries=1)
    kwargs: dict = {"model": modelo, "max_tokens": MAX_TOKENS, "system": system,
                    "messages": _mensagens_para_anthropic(mensagens)}
    if ferramentas:
        kwargs["tools"] = ferramentas
    try:
        resposta = cliente.messages.create(**kwargs)
    except anthropic.APITimeoutError as e:
        raise _com_detalhe(_erro("timeout"), e) from None
    except anthropic.APIConnectionError as e:
        raise _com_detalhe(_erro("rede"), e) from None
    except anthropic.APIStatusError as e:
        raise _com_detalhe(classificar_http(e.status_code, str(getattr(e, "message", "") or e), modelo), e) from None

    texto = "".join(b.text for b in resposta.content if b.type == "text")
    chamadas = [
        {"id": b.id, "name": b.name, "arguments": dict(b.input) if isinstance(b.input, dict) else {}}
        for b in resposta.content if b.type == "tool_use"
    ]
    out: dict = {"role": "assistant", "content": texto or None}
    if chamadas:
        out["tool_calls"] = chamadas
    elif out["content"] is None:
        out["content"] = ""
    return out



ERROS_QUE_VALEM_TENTAR_DE_NOVO = ("indisponivel", "limite", "timeout", "rede")


def _modelos_reserva() -> list[str]:
    """ASSISTENTE_MODELOS_RESERVA: modelos do OpenRouter (separados por vírgula) usados
    quando o principal está sobrecarregado/indisponível (típico de modelos gratuitos)."""
    bruto = os.environ.get("ASSISTENTE_MODELOS_RESERVA") or ""
    return [m.strip() for m in bruto.split(",") if m.strip()]


def _completar_openrouter_com_reserva(system: str, mensagens: list[dict], ferramentas: list[dict], modelo: str) -> dict:
    """Tenta o modelo principal (com 1 nova tentativa curta se estiver sobrecarregado)
    e, se continuar falhando por indisponibilidade/limite, passa pelos modelos reserva.
    Erros de chave, saldo, modelo inexistente ou configuração NÃO são repetidos."""
    modelos = [modelo] + [m for m in _modelos_reserva() if m != modelo]
    ultimo: ErroAssistente | None = None
    for i, m in enumerate(modelos):
        tentativas = 2 if i == 0 else 1
        for t in range(tentativas):
            try:
                return _completar_openrouter(system, mensagens, ferramentas, m)
            except ErroAssistente as e:
                ultimo = e
                if e.tipo not in ERROS_QUE_VALEM_TENTAR_DE_NOVO:
                    raise
                if t + 1 < tentativas:
                    _pausar(PAUSA_ENTRE_TENTATIVAS_S)
    assert ultimo is not None
    raise ultimo


PAUSA_ENTRE_TENTATIVAS_S = 2.0


def _pausar(segundos: float) -> None:
    import time
    time.sleep(segundos)


# ---------------------------------------------------------------------------
# Entrada única
# ---------------------------------------------------------------------------
def completar(system: str, mensagens: list[dict], ferramentas: list[dict]) -> dict:
    """Uma rodada de completion. Devolve a mensagem 'assistant' neutra.
    Levanta ErroAssistente (já registrado em log/status) em qualquer falha."""
    cfg = configuracao()
    if not cfg["configurado"]:
        e = ErroAssistente("configuracao", cfg["motivo"] or "Assistente de IA não configurado.")
        _registrar_erro(e, cfg["provedor"], cfg["modelo"], cfg["motivo"] or "")
        raise e
    try:
        if cfg["provedor"] == PROVEDOR_OPENROUTER:
            out = _completar_openrouter_com_reserva(system, mensagens, ferramentas, cfg["modelo"])
        else:
            out = _completar_anthropic(system, mensagens, ferramentas, cfg["modelo"])
    except ErroAssistente as e:
        _registrar_erro(e, cfg["provedor"], cfg["modelo"], getattr(e, "_detalhe_log", ""))
        raise
    except Exception as e:  # nunca deixa um erro inesperado do provedor virar 500 cru
        err = _erro("resposta_invalida")
        _registrar_erro(err, cfg["provedor"], cfg["modelo"], f"{type(e).__name__}: {e}")
        raise err from None
    _registrar_sucesso()
    return out
