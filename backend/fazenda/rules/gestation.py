"""
Regras de gestação — calcula data provável de parto por raça.

Dias de gestação por raça (validados com o dono):
  Holandês            280 dias
  Girolando           287 dias
  Gir / Zebu / GO     295 dias
  (padrão para raças não mapeadas: 287 dias)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


# Dias de gestação por raça (mapeamento normalizado → chave lowercase sem acento)
GESTACAO_DIAS: dict[str, int] = {
    "holandes": 280,
    "holandês": 280,
    "girolando": 287,
    "gir": 295,
    "zebu": 295,
    "nelore": 295,
    "guzerá": 295,
    "guzera": 295,
    "gir/zebu": 295,
}

DEFAULT_GESTACAO = 287  # Girolando como padrão


def dias_gestacao(raca: str | None) -> int:
    """Retorna o número de dias de gestação para a raça informada."""
    if not raca:
        return DEFAULT_GESTACAO
    raca_norm = raca.strip().lower()
    for chave, dias in GESTACAO_DIAS.items():
        if chave in raca_norm:
            return dias
    return DEFAULT_GESTACAO


@dataclass
class ResultadoGestacao:
    data_parto_provavel: date
    dias_gestacao: int
    raca: str | None
    data_servico: date


def calcular_parto_provavel(
    data_servico: date,
    raca: str | None,
) -> ResultadoGestacao:
    """
    Calcula a data provável de parto para um serviço positivo (IA/IATF/Cobertura).

    Args:
        data_servico: Data do serviço que resultou em prenhez confirmada.
        raca: Raça da matriz (ex. 'Girolando', 'Holandês', 'Gir').

    Returns:
        ResultadoGestacao com data provável e metadados.
    """
    dias = dias_gestacao(raca)
    return ResultadoGestacao(
        data_parto_provavel=data_servico + timedelta(days=dias),
        dias_gestacao=dias,
        raca=raca,
        data_servico=data_servico,
    )
