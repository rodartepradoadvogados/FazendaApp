#!/usr/bin/env python3
"""
Ponte MCP (stdio) SOMENTE LEITURA entre o Hermes Agent e o CowData.

Cada ferramenta de GET /agente/ferramentas vira uma ferramenta MCP com o
mesmo nome, descricao e parametros (registradas dinamicamente na partida),
mais `instrucoes_cowdata` (GET /agente/instrucoes: prompt base + Ensinamentos).
So faz requisicoes GET. Nao existe nenhuma ferramenta de escrita.

Variaveis de ambiente (nomes exatos):
  COWDATA_API_URL        ex.: https://fazendaapp-production.up.railway.app
  COWDATA_AGENTE_TOKEN   mesmo valor de AGENTE_API_TOKEN no Railway (NUNCA no codigo)
  COWDATA_TIMEOUT        segundos por requisicao (padrao 30)

Se a API estiver fora do ar na partida, sobe em modo degradado com
`consultar_cowdata(ferramenta, parametros)` + `instrucoes_cowdata` (reinicie o MCP
para recarregar a lista, ex.: /reload-mcp no Hermes).
"""
from __future__ import annotations

import inspect
import json
import os
import sys
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

TIPOS = {"string": str, "integer": int, "number": float, "boolean": bool}
MSG_INDISPONIVEL = "O CowData nao respondeu agora. Tente novamente em instantes."


def _log(msg: str) -> None:
    print(f"[mcp-cowdata] {msg}", file=sys.stderr, flush=True)  # stdout e' o canal MCP: nunca imprimir nele


def _criar_cliente() -> httpx.Client:
    url = (os.environ.get("COWDATA_API_URL") or "").rstrip("/")
    token = os.environ.get("COWDATA_AGENTE_TOKEN") or ""
    if not url or not token:
        raise RuntimeError("Defina COWDATA_API_URL e COWDATA_AGENTE_TOKEN no ambiente do MCP.")
    timeout = float(os.environ.get("COWDATA_TIMEOUT") or 30)
    return httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)


def _get(caminho: str, params: dict | None = None) -> dict:
    """GET na API do CowData. Devolve sempre um dict; erros viram {"erro": "..."}
    em portugues, sem vazar token/URL interna."""
    try:
        with _criar_cliente() as c:
            r = c.get(caminho, params={k: v for k, v in (params or {}).items() if v is not None})
    except RuntimeError as e:
        return {"erro": str(e)}
    except httpx.TimeoutException:
        return {"erro": "O CowData demorou demais para responder (timeout). " + MSG_INDISPONIVEL}
    except httpx.HTTPError:
        return {"erro": "Falha de rede ao falar com o CowData. " + MSG_INDISPONIVEL}
    if r.status_code == 200:
        try:
            return r.json()
        except ValueError:
            return {"erro": "Resposta invalida do CowData."}
    try:
        detalhe = r.json().get("detail")
    except Exception:
        detalhe = None
    mapa = {
        401: "Token do agente recusado pelo CowData (verifique COWDATA_AGENTE_TOKEN).",
        403: "Acesso recusado (IP nao permitido em AGENTE_IPS_PERMITIDOS?).",
        404: "API de leitura desativada ou ferramenta inexistente no CowData.",
        429: "Limite de consultas por minuto atingido. Aguarde um instante.",
    }
    if r.status_code in mapa:
        return {"erro": mapa[r.status_code] + (f" ({detalhe})" if detalhe and r.status_code in (404,) else "")}
    if r.status_code == 400:
        return {"erro": f"Parametros invalidos: {detalhe}"}
    return {"erro": f"O CowData devolveu erro {r.status_code}. " + MSG_INDISPONIVEL}


def _como_texto(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False, default=str)


def _fabricar(nome: str, descricao: str, esquema: dict):
    """Cria uma funcao com a assinatura dos parametros da ferramenta (para o
    FastMCP gerar o schema) que repassa tudo para /agente/consultar/{nome}."""
    props: dict = esquema.get("properties") or {}
    obrigatorios = [p for p in props if p in (esquema.get("required") or [])]
    opcionais = [p for p in props if p not in obrigatorios]
    params = []
    for p in obrigatorios:
        params.append(inspect.Parameter(p, inspect.Parameter.KEYWORD_ONLY, annotation=TIPOS.get(props[p].get("type"), str)))
    for p in opcionais:
        params.append(inspect.Parameter(p, inspect.Parameter.KEYWORD_ONLY, default=None,
                                        annotation=Optional[TIPOS.get(props[p].get("type"), str)]))
    params.append(inspect.Parameter("limite", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=Optional[int]))
    params.append(inspect.Parameter("offset", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=Optional[int]))

    def ferramenta(**kwargs: Any) -> str:
        return _como_texto(_get(f"/agente/consultar/{nome}", kwargs))

    ferramenta.__name__ = nome
    ferramenta.__signature__ = inspect.Signature(params, return_annotation=str)  # type: ignore[attr-defined]
    ferramenta.__annotations__ = {p.name: p.annotation for p in params} | {"return": str}
    ferramenta.__doc__ = (
        f"{descricao}\n\n(Somente leitura. 'limite' e 'offset' paginam listas grandes; "
        "se a resposta vier com truncado=true, repita com offset maior.)"
    )
    return ferramenta


def construir_servidor() -> FastMCP:
    mcp = FastMCP("cowdata-leitura")

    @mcp.tool(name="instrucoes_cowdata", description=(
        "Devolve as instrucoes oficiais do CowData para o agente (prompt base + Ensinamentos ativos da fazenda). "
        "Leia no inicio da conversa e quando o dono disser que ensinou algo novo."))
    def instrucoes_cowdata() -> str:
        return _como_texto(_get("/agente/instrucoes"))

    lista = _get("/agente/ferramentas")
    ferramentas = lista.get("ferramentas") if isinstance(lista, dict) else None
    if not ferramentas:
        _log(f"nao consegui listar as ferramentas ({lista.get('erro') if isinstance(lista, dict) else '?'}); modo degradado")

        @mcp.tool(name="consultar_cowdata", description=(
            "Consulta generica (somente leitura) ao CowData: ferramenta = nome da consulta; parametros = objeto JSON "
            "com os parametros dela (ex.: {\"numero\": \"123\"}). Modo degradado: a lista de ferramentas nao carregou."))
        def consultar_cowdata(ferramenta: str, parametros: Optional[dict] = None) -> str:
            return _como_texto(_get(f"/agente/consultar/{ferramenta}", parametros or {}))
        return mcp

    for f in ferramentas:
        mcp.add_tool(_fabricar(f["nome"], f.get("descricao", ""), f.get("parametros") or {}),
                     name=f["nome"], description=f.get("descricao", ""))
    _log(f"{len(ferramentas)} ferramentas de leitura registradas")
    return mcp


if __name__ == "__main__":
    construir_servidor().run(transport="stdio")
