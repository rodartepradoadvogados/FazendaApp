"""Calendário sanitário — projeção da próxima ocorrência de uma regra recorrente."""
from __future__ import annotations

import calendar
from datetime import date, timedelta


def _somar_meses(d: date, meses: int) -> date:
    total = d.month - 1 + meses
    ano = d.year + total // 12
    mes = total % 12 + 1
    dia = min(d.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def proxima_ocorrencia(data_evento: date, frequencia_valor: int, frequencia_unidade: str) -> date:
    """Data de referência + a recorrência configurada (dias/meses/anos)."""
    if frequencia_unidade == "dias":
        return data_evento + timedelta(days=frequencia_valor)
    if frequencia_unidade == "meses":
        return _somar_meses(data_evento, frequencia_valor)
    if frequencia_unidade == "anos":
        return _somar_meses(data_evento, frequencia_valor * 12)
    raise ValueError(f"Unidade de frequência inválida: {frequencia_unidade}")
