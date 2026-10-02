"""
Núcleo da API de leitura para agentes externos (Hermes) — /agente/*.

Tudo aqui é lógica sem rota (a rota fica em api/routers/agente_leitura.py):

- Ativação/autenticação: só existe com AGENTE_API_TOKEN (>= 32 chars); sem ela
  o router responde 404 (como se não existisse). Comparação em tempo constante.
- Fazenda alvo FIXA por AGENTE_FAZENDA_ID (padrão 1) — o agente nunca escolhe.
- AGENTE_IPS_PERMITIDOS (opcional): lista separada por vírgula.
- Rate limit em memória por processo (AGENTE_RATE_LIMIT_POR_MIN, padrão 60) e
  contador separado, mais apertado, para tentativas com token errado.
- Sessão de banco SOMENTE LEITURA (PRAGMA query_only no SQLite / SET
  TRANSACTION READ ONLY no PostgreSQL) + trava em Python (commit/flush
  proibidos) + rollback sempre.
- Saída sanitizada (`sanitizar`): remove segredos/dados bancários/e-mails e
  mascara CPF/CNPJ. Lista completa em docs/agentes/hermes-cowdata/.
- Paginação/truncamento de listas grandes.
- Auditoria: uma linha de log por chamada (logger `fazenda.agente_auditoria`)
  e um anel em memória das últimas chamadas. NUNCA grava o token.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
from collections import deque
from contextlib import suppress
from datetime import datetime, timezone

from sqlalchemy import event
from sqlmodel import Session, text

logger = logging.getLogger("fazenda.agente_auditoria")

TOKEN_TAMANHO_MINIMO = 32
LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200
MAX_BYTES_PADRAO = 100_000
RATE_LIMIT_PADRAO = 60
FALHAS_POR_MINUTO = 10
PARAMETROS_RESERVADOS = ("limite", "offset")


class SomenteLeituraError(Exception):
    """Tentativa de escrita numa sessão somente leitura."""


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def _token_configurado() -> str | None:
    t = (os.environ.get("AGENTE_API_TOKEN") or "").strip()
    return t if len(t) >= TOKEN_TAMANHO_MINIMO else None


def agente_ativado() -> bool:
    return _token_configurado() is not None


def fazenda_alvo_id() -> int:
    try:
        return int((os.environ.get("AGENTE_FAZENDA_ID") or "1").strip())
    except ValueError:
        return 1


def ips_permitidos() -> set[str]:
    return {p.strip() for p in (os.environ.get("AGENTE_IPS_PERMITIDOS") or "").split(",") if p.strip()}


def modulos_permitidos() -> set[str] | None:
    """AGENTE_MODULOS (opcional): restringe as ferramentas aos módulos listados.
    Ausente = todas as ferramentas (mesmo que um administrador teria)."""
    bruto = (os.environ.get("AGENTE_MODULOS") or "").strip()
    return {m.strip() for m in bruto.split(",") if m.strip()} if bruto else None


def limite_por_minuto() -> int:
    try:
        return max(1, int(os.environ.get("AGENTE_RATE_LIMIT_POR_MIN") or RATE_LIMIT_PADRAO))
    except ValueError:
        return RATE_LIMIT_PADRAO


def max_bytes() -> int:
    try:
        return max(500, int(os.environ.get("AGENTE_MAX_BYTES") or MAX_BYTES_PADRAO))
    except ValueError:
        return MAX_BYTES_PADRAO


# ---------------------------------------------------------------------------
# Autenticação / IP
# ---------------------------------------------------------------------------
def token_valido(authorization: str | None) -> bool:
    esperado = _token_configurado()
    if not esperado or not authorization:
        return False
    partes = authorization.split(" ", 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return False
    return hmac.compare_digest(partes[1].strip().encode("utf-8"), esperado.encode("utf-8"))


def ip_do_cliente(x_forwarded_for: str | None, host: str | None) -> str:
    """IP do cliente atrás do proxy. Usa a entrada MAIS À DIREITA do
    X-Forwarded-For (a que o último proxy confiável acrescentou) — a da
    esquerda pode ser forjada pelo próprio cliente. Sem o cabeçalho, o IP da
    conexão. (Com mais de um proxy na frente, a da direita seria de um proxy
    interno e a lista de IPs falharia fechada.)"""
    if x_forwarded_for:
        partes = [p.strip() for p in x_forwarded_for.split(",") if p.strip()]
        if partes:
            return partes[-1]
    return host or "desconhecido"


def ip_permitido(ip: str) -> bool:
    lista = ips_permitidos()
    return not lista or ip in lista


# ---------------------------------------------------------------------------
# Rate limit (janela deslizante de 60 s, em memória deste processo)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_janelas: dict[str, deque] = {}
_ultimas: deque = deque(maxlen=200)


def _resetar_estado_para_testes() -> None:
    with _lock:
        _janelas.clear()
        _ultimas.clear()


def _estourou(chave: str, limite: int) -> int:
    """0 se ainda cabe (e registra o uso); senão os segundos até liberar."""
    agora = time.monotonic()
    with _lock:
        fila = _janelas.setdefault(chave, deque())
        while fila and agora - fila[0] >= 60:
            fila.popleft()
        if len(fila) >= limite:
            return max(1, int(60 - (agora - fila[0])) + 1)
        fila.append(agora)
        return 0


def verificar_limite_token_valido(token: str) -> int:
    chave = "ok:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return _estourou(chave, limite_por_minuto())


def verificar_limite_falhas(ip: str) -> int:
    return _estourou("falha:" + ip, FALHAS_POR_MINUTO)


# ---------------------------------------------------------------------------
# Sessão somente leitura
# ---------------------------------------------------------------------------
def _travar_escrita(*_a, **_k):
    raise SomenteLeituraError("Sessão somente leitura: escrita bloqueada.")


def sessao_somente_leitura(session: Session):
    """Dependência (generator): coloca a sessão em modo SOMENTE LEITURA e,
    no final, faz rollback e devolve a conexão ao estado normal.

    Três camadas: (1) o banco recusa escrita (SQLite: PRAGMA query_only=ON;
    PostgreSQL: SET TRANSACTION READ ONLY); (2) `commit` e o flush de
    qualquer objeto novo/alterado/apagado levantam SomenteLeituraError;
    (3) nunca há commit — sempre rollback."""
    dialeto = session.get_bind().dialect.name
    session.rollback()  # recomeça uma transação limpa
    if dialeto == "sqlite":
        session.exec(text("PRAGMA query_only=ON"))
    elif dialeto == "postgresql":
        session.exec(text("SET TRANSACTION READ ONLY"))
    else:  # dialeto desconhecido: falha fechada
        raise SomenteLeituraError(f"Dialeto sem modo somente leitura conhecido: {dialeto}")

    event.listen(session, "before_flush", _travar_escrita)
    comit_original = session.__dict__.get("commit")
    session.commit = _travar_escrita  # type: ignore[method-assign]
    try:
        yield session
    finally:
        with suppress(Exception):
            session.rollback()
        event.remove(session, "before_flush", _travar_escrita)
        if comit_original is None:
            session.__dict__.pop("commit", None)
        else:
            session.commit = comit_original  # type: ignore[method-assign]
        if dialeto == "sqlite":
            with suppress(Exception):
                session.exec(text("PRAGMA query_only=OFF"))
                session.rollback()


# ---------------------------------------------------------------------------
# Sanitização da saída
# ---------------------------------------------------------------------------
_CHAVES_SUBSTRING = (
    "senha", "password", "passwd", "hash", "token", "secret", "segredo", "api_key", "apikey",
    "authorization", "email", "e_mail", "conta_bancaria", "cartao", "agencia",
)
_CHAVES_PALAVRA = re.compile(r"(?:^|_)(?:pix|banco|iban|cvv|cvc|swift)(?:_|$)")
_CHAVE_DOC = re.compile(r"(?:^|_)(cpf|cnpj)(?:_|$)")
_RE_CPF = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-(\d{2})(?!\d)")
_RE_CNPJ = re.compile(r"(?<!\d)\d{2}\.\d{3}\.\d{3}/\d{4}-(\d{2})(?!\d)")
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _chave_sensivel(chave: str) -> bool:
    k = chave.lower()
    return any(s in k for s in _CHAVES_SUBSTRING) or bool(_CHAVES_PALAVRA.search(k))


def _mascarar_texto(t: str) -> str:
    t = _RE_CNPJ.sub(lambda m: f"**.***.***/****-{m.group(1)}", t)
    t = _RE_CPF.sub(lambda m: f"***.***.***-{m.group(1)}", t)
    return _RE_EMAIL.sub("[e-mail oculto]", t)


def _mascarar_documento(valor) -> str:
    digitos = re.sub(r"\D", "", str(valor))
    if len(digitos) == 11:
        return f"***.***.***-{digitos[-2:]}"
    if len(digitos) == 14:
        return f"**.***.***/****-{digitos[-2:]}"
    return "***"


def sanitizar(obj):
    """Remove chaves sensíveis (em qualquer nível), mascara valores de chaves
    cpf/cnpj e CPF/CNPJ/e-mail que apareçam em texto livre."""
    if isinstance(obj, dict):
        saida = {}
        for k, v in obj.items():
            ks = str(k)
            if _chave_sensivel(ks):
                continue
            if _CHAVE_DOC.search(ks.lower()):
                if v is not None:
                    saida[k] = _mascarar_documento(v)
                else:
                    saida[k] = None
                continue
            saida[k] = sanitizar(v)
        return saida
    if isinstance(obj, (list, tuple)):
        return [sanitizar(i) for i in obj]
    if isinstance(obj, str):
        return _mascarar_texto(obj)
    return obj


# ---------------------------------------------------------------------------
# Paginação / truncamento
# ---------------------------------------------------------------------------
def _fatiar(obj, limite: int, offset: int, caminho: str, info: dict, profundidade: int):
    if isinstance(obj, list):
        total = len(obj)
        fatia = obj[offset:offset + limite]
        if total > limite or offset > 0:
            info[caminho or "(raiz)"] = {"total": total, "retornados": len(fatia)}
        return fatia
    if isinstance(obj, dict) and profundidade < 2:
        return {
            k: _fatiar(v, limite, offset, f"{caminho}.{k}" if caminho else str(k), info, profundidade + 1)
            if isinstance(v, (list, dict)) else v
            for k, v in obj.items()
        }
    return obj


def paginar(resultado, limite: int, offset: int, maximo_bytes: int) -> dict:
    """Aplica limite/offset a cada lista do resultado (até 2 níveis) e, se o
    JSON ainda passar de `maximo_bytes`, vai reduzindo o limite pela metade.
    Devolve {"resultado", "truncado", "paginacao"}."""
    limite = max(1, min(limite, LIMITE_MAXIMO))
    offset = max(0, offset)
    motivo_tamanho = False
    while True:
        info: dict = {}
        fatiado = _fatiar(resultado, limite, offset, "", info, 0)
        truncado = any(v["total"] > offset + v["retornados"] for v in info.values())
        envelope = {
            "resultado": fatiado,
            "truncado": truncado or motivo_tamanho,
            "paginacao": {"limite": limite, "offset": offset, "listas": info},
        }
        tamanho = len(json.dumps(envelope, ensure_ascii=False, default=str).encode("utf-8"))
        if tamanho <= maximo_bytes or limite <= 1:
            if motivo_tamanho:
                envelope["paginacao"]["motivo"] = "tamanho"
            return envelope
        limite = max(1, limite // 2)
        motivo_tamanho = True


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------
def _resumir_parametros(params: dict) -> str:
    try:
        txt = json.dumps({k: str(v)[:60] for k, v in params.items()}, ensure_ascii=False)
    except Exception:
        txt = "?"
    return txt[:200]


def auditar(ferramenta: str, params: dict, ip: str, status: int, duracao_ms: int) -> None:
    resumo = _resumir_parametros(params)
    registro = {
        "em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ferramenta": ferramenta, "parametros": resumo, "ip": ip, "status": status, "duracao_ms": duracao_ms,
    }
    with _lock:
        _ultimas.append(registro)
    logger.info(
        "agente_leitura ferramenta=%s params=%s ip=%s status=%s duracao_ms=%s",
        ferramenta, resumo, ip, status, duracao_ms,
    )


def ultimas_chamadas() -> list[dict]:
    with _lock:
        return list(_ultimas)
