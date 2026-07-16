"""
Regras de Scratch (adesivo) e PEV.

SCRATCH (adesivo):
  - Aplicar 14 dias após o ÚLTIMO serviço do animal.
  - "Novo cio zera o anterior" → só o serviço mais recente conta.
  - Diagnóstico NEGATIVO cancela o scratch (a inseminação não conta prazo).

PEV (Período de Espera Voluntário):
  - pev_dias (editável em Configurações > Parâmetros, padrão 45) após o
    parto — quando o animal está liberado para inseminar.
  - Emitir aviso só se o animal ainda não está gestante.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from fazenda.rules.parametros import pev_dias

DIAS_SCRATCH = 14


@dataclass
class ResultadoScratch:
    data_scratch: date
    data_servico: date
    numero_matriz: str
    ativo: bool
    motivo_cancelamento: str | None = None


@dataclass
class ResultadoPEV:
    data_pev: date           # data em que o PEV termina (animal liberado)
    data_parto: date
    numero_matriz: str
    liberado: bool           # True se hoje >= data_pev
    dias_restantes: int      # dias até o PEV terminar (0 se já liberado)


def calcular_scratch(
    numero_matriz: str,
    data_ultimo_servico: date,
    diagnostico_ultimo: str | None,
) -> ResultadoScratch:
    """
    Calcula o evento de scratch para o animal.

    Args:
        numero_matriz: Identificador do animal.
        data_ultimo_servico: Data do serviço mais recente (ÚLT_OCORR=1).
        diagnostico_ultimo: Resultado do diagnóstico do último serviço
                            ('POSITIVO' / 'NEGATIVO' / 'ABERTO' / None).

    Returns:
        ResultadoScratch. Se ativo=False, NÃO gerar evento na agenda.
    """
    data_scratch = data_ultimo_servico + timedelta(days=DIAS_SCRATCH)
    diagnostico_norm = (diagnostico_ultimo or "").upper().strip()

    if diagnostico_norm == "NEGATIVO":
        return ResultadoScratch(
            data_scratch=data_scratch,
            data_servico=data_ultimo_servico,
            numero_matriz=numero_matriz,
            ativo=False,
            motivo_cancelamento="Diagnóstico NEGATIVO — inseminação não conta prazo de scratch",
        )

    return ResultadoScratch(
        data_scratch=data_scratch,
        data_servico=data_ultimo_servico,
        numero_matriz=numero_matriz,
        ativo=True,
    )


def calcular_pev(
    numero_matriz: str,
    data_parto: date,
    data_referencia: date | None = None,
) -> ResultadoPEV:
    """
    Calcula o PEV (Período de Espera Voluntário) — 45 dias após o parto.

    Args:
        numero_matriz: Identificador do animal.
        data_parto: Data do último parto.
        data_referencia: Data de referência para calcular dias restantes (default: hoje).

    Returns:
        ResultadoPEV com data de liberação e status.
    """
    hoje = data_referencia or date.today()
    data_pev = data_parto + timedelta(days=pev_dias())
    dias_restantes = max(0, (data_pev - hoje).days)

    return ResultadoPEV(
        data_pev=data_pev,
        data_parto=data_parto,
        numero_matriz=numero_matriz,
        liberado=hoje >= data_pev,
        dias_restantes=dias_restantes,
    )
