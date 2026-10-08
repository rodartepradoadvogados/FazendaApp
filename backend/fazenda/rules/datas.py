"""
"Hoje" no fuso da fazenda — Fase A, R5 (ver docs/financeiro-regras-v2.md).

POR QUE ISTO EXISTE. O servidor de produção (Railway) roda em UTC. `date.today()`
ali vira o dia seguinte às 21h de Brasília: das 21h à meia-noite, o Caixa Real,
Contas a pagar e o "vencido/a vencer" do cartão enxergavam o dia de AMANHÃ. O
front já resolve isso com `hojeLocal()` (lib), que nunca usa `toISOString`;
este módulo é o espelho no backend.

O Brasil não tem horário de verão desde 2019, então o fallback para um fuso
fixo de −3h (quando a base de fusos do sistema não existir no container) dá o
mesmo resultado que `America/Sao_Paulo`.

Uso: só nos pontos de "hoje" do FINANCEIRO (financeiro.py, cartao_credito.py).
O resto do sistema continua com `date.today()` até ser migrado de propósito.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

try:  # pragma: no cover - depende da base de fusos do sistema
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        FUSO_FAZENDA = ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        FUSO_FAZENDA = timezone(timedelta(hours=-3), "BRT")
except ImportError:  # pragma: no cover
    FUSO_FAZENDA = timezone(timedelta(hours=-3), "BRT")


# Só para a SUÍTE DE TESTES (tests/conftest.py liga): "relogio_local" faz o
# relógio real seguir o fuso da máquina, igual ao `date.today()` que os testes
# antigos usam para montar as datas esperadas. Sem isso, a suíte rodada entre
# 00h e 03h UTC (CI) veria "hoje" diferente do servidor e falharia por acaso.
# Nunca definida em produção. Chamadas com `agora` explícito ignoram a chave.
_ENV_RELOGIO = "FAZENDA_HOJE_LOCAL_RELOGIO"


def agora_local(agora: datetime | None = None) -> datetime:
    """Data e hora em Brasília. `agora` (com fuso) serve aos testes; sem fuso,
    é tratado como UTC — que é o relógio do servidor."""
    if agora is None:
        if os.environ.get(_ENV_RELOGIO) == "relogio_local":
            return datetime.now()
        agora = datetime.now(timezone.utc)
    elif agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    return agora.astimezone(FUSO_FAZENDA)


def hoje_local(agora: datetime | None = None) -> date:
    """O dia de hoje em Brasília (não em UTC). Ex.: 08/10 às 23h30 de Brasília
    = 09/10 02h30 UTC → devolve 08/10."""
    return agora_local(agora).date()
