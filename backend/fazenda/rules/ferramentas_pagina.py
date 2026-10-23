"""Ferramentas com que o assistente OLHA e OPERA a tela do próprio usuário.

Por que a automação roda no navegador de quem pergunta, e não num Chromium
no servidor (decisão de 22/10/2026, depois de checar as premissas do plano
de MCP):

1. O backend roda no Railway (região sfo) e o Hermes roda na VPS — não existe
   `localhost` comum aos dois. Um transporte `stdio` obrigaria a instalar
   Hermes + Chromium DENTRO da imagem do backend, que é exatamente o custo
   (~500 MB de RAM) que o plano queria evitar.
2. `hermes mcp serve` NÃO exporta ferramentas de browser: ele expõe conversas
   (`conversations_list`, `conversation_get`, `messages_read`,
   `attachments_fetch`, `events_poll`, `events_wait`, `messages_send`,
   `channels_list` — ver /usr/local/lib/hermes-agent/mcp_serve.py). Não há
   `browser_navigate`/`browser_click` do lado servidor para consumir.
3. Um browser no servidor navegaria com a sessão de QUEM configurou o vault.
   Qualquer usuário logado da fazenda (um funcionário, um contador) passaria a
   ver as telas do dono: vazamento entre pessoas, não entre fazendas.

O desenho daqui usa o que já existe: o backend devolve as chamadas pendentes
(`aguardando`) e o frontend executa no DOM da própria aba, devolvendo os
resultados em `resultados_pagina` na requisição seguinte. A sessão é sempre a
de quem perguntou, não há Chromium em lugar nenhum e o custo é zero.

Segurança: `pagina_navegar` só aceita caminho relativo começando com "/".
URL absoluta, "//host" (protocol-relative) ou esquema são recusados — o
modelo não consegue tirar o usuário do app nem fazer o navegador buscar um
site externo. Os seletores/valores são apenas repassados ao DOM da aba; quem
executa é o próprio app.
"""
from __future__ import annotations

from typing import Any

NOMES: frozenset[str] = frozenset({
    "pagina_info",
    "pagina_navegar",
    "pagina_ler",
    "pagina_clicar",
    "pagina_preencher",
    "pagina_esperar",
})

_SPECS: list[dict] = [
    {
        "name": "pagina_info",
        "description": (
            "Diz em que tela o usuário está agora (caminho, título, se terminou de carregar). "
            "Use antes de qualquer outra ferramenta de página quando não souber onde ele está."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "pagina_navegar",
        "description": (
            "Leva o usuário para uma tela do próprio app (ex.: '/alimentacao/dietas', "
            "'/lancamentos'). Só caminho interno — aceita apenas caminho relativo começando com '/'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho interno, ex.: '/alimentacao/dietas'."},
            },
            "required": ["caminho"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pagina_ler",
        "description": (
            "Lê o texto visível de um trecho da tela atual (por seletor CSS) para você enxergar o que o "
            "usuário está vendo. Padrão: 'main'. Use quando a pergunta for sobre o que aparece na tela."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seletor": {"type": "string", "description": "Seletor CSS. Padrão 'main'."},
                "limite": {"type": "integer", "description": "Máximo de caracteres. Padrão 4000."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "pagina_clicar",
        "description": "Clica num elemento da tela atual (botão, aba, link interno).",
        "input_schema": {
            "type": "object",
            "properties": {
                "seletor": {"type": "string", "description": "Seletor CSS do elemento."},
            },
            "required": ["seletor"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pagina_preencher",
        "description": "Preenche um campo de texto da tela atual (input, textarea, select).",
        "input_schema": {
            "type": "object",
            "properties": {
                "seletor": {"type": "string", "description": "Seletor CSS do campo."},
                "valor": {"type": "string", "description": "Texto a digitar."},
                "enviar": {"type": "boolean", "description": "Pressionar Enter depois. Padrão false."},
            },
            "required": ["seletor", "valor"],
            "additionalProperties": False,
        },
    },
    {
        "name": "pagina_esperar",
        "description": "Espera um elemento aparecer na tela atual (útil depois de clicar/navegar).",
        "input_schema": {
            "type": "object",
            "properties": {
                "seletor": {"type": "string", "description": "Seletor CSS do elemento esperado."},
                "timeout_ms": {"type": "integer", "description": "Tempo máximo em ms. Padrão 8000."},
            },
            "required": ["seletor"],
            "additionalProperties": False,
        },
    },
]


def especificacoes() -> list[dict]:
    """Specs no formato Anthropic (input_schema), como as demais ferramentas."""
    return _SPECS


def caminho_seguro(caminho: Any) -> str | None:
    """Caminho interno aceitável, ou None. Só relativo: '/...' simples."""
    if not isinstance(caminho, str):
        return None
    caminho = caminho.strip()
    if not caminho.startswith("/"):
        return None
    if caminho.startswith("//"):          # protocol-relative (//host)
        return None
    if "\\" in caminho or "://" in caminho or " " in caminho:
        return None
    if len(caminho) > 300:
        return None
    return caminho


def _texto(valor: Any, campo: str, *, maximo: int = 300) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"'{campo}' precisa ser um texto não vazio")
    valor = valor.strip()
    if len(valor) > maximo:
        raise ValueError(f"'{campo}' passou de {maximo} caracteres")
    return valor


def validar(nome: str, argumentos: dict) -> dict:
    """Normaliza/valida os argumentos de uma ferramenta de página.

    Levanta ValueError com mensagem em português — o chamador transforma isso
    em resultado de ferramenta com `erro`, para o modelo se corrigir, em vez
    de derrubar a conversa.
    """
    if nome not in NOMES:
        raise ValueError(f"ferramenta de página desconhecida: {nome}")
    args = dict(argumentos or {})

    if nome == "pagina_info":
        return {}

    if nome == "pagina_navegar":
        caminho = caminho_seguro(args.get("caminho"))
        if caminho is None:
            raise ValueError("'caminho' precisa ser interno e relativo, ex.: '/alimentacao/dietas'")
        return {"caminho": caminho}

    if nome == "pagina_ler":
        seletor = args.get("seletor") or "main"
        limite = args.get("limite", 4000)
        if not isinstance(limite, int) or not 100 <= limite <= 20000:
            raise ValueError("'limite' precisa ser um inteiro entre 100 e 20000")
        return {"seletor": _texto(seletor, "seletor"), "limite": limite}

    if nome in ("pagina_clicar", "pagina_esperar"):
        norm: dict[str, Any] = {"seletor": _texto(args.get("seletor"), "seletor")}
        if nome == "pagina_esperar":
            timeout = args.get("timeout_ms", 8000)
            if not isinstance(timeout, int) or not 100 <= timeout <= 30000:
                raise ValueError("'timeout_ms' precisa ser um inteiro entre 100 e 30000")
            norm["timeout_ms"] = timeout
        return norm

    # pagina_preencher
    return {
        "seletor": _texto(args.get("seletor"), "seletor"),
        "valor": args.get("valor") if isinstance(args.get("valor"), str) else "",
        "enviar": bool(args.get("enviar", False)),
    }
