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
    """Data de referência + a recorrência configurada (dias/meses/anos) — UM
    passo adiante, sempre. Uso correto: rolar uma série já em andamento (ver
    `_ocorrencias_recorrentes` em rules/eventos_sanitarios.py, que soma a
    partir da própria `data_evento` DEPOIS de já ter incluído ela mesma como
    1ª ocorrência). Para "qual é a próxima ocorrência a partir de hoje" de uma
    regra ainda não materializada, use `proxima_ocorrencia_a_partir_de` — não
    esta função direto, ou o 1º ciclo é pulado (ver docstring de lá)."""
    if frequencia_unidade == "dias":
        return data_evento + timedelta(days=frequencia_valor)
    if frequencia_unidade == "meses":
        return _somar_meses(data_evento, frequencia_valor)
    if frequencia_unidade == "anos":
        return _somar_meses(data_evento, frequencia_valor * 12)
    raise ValueError(f"Unidade de frequência inválida: {frequencia_unidade}")


def proxima_ocorrencia_a_partir_de(data_evento: date, frequencia_valor: int, frequencia_unidade: str, hoje: date) -> date:
    """A próxima ocorrência de verdade, olhando a partir de hoje: `data_evento`
    é a data de REFERÊNCIA (a 1ª ocorrência, não a última) — se ela ainda não
    passou, ela MESMA é a próxima, sem somar a frequência por cima (mesmo bug
    relatado pelo usuário em 12/09/2026 já corrigido para `usa_cronograma=True`
    em `rules/cronograma_sanitario.py::cronograma_aberto`; aqui é a mesma causa
    para o caso comum, `usa_cronograma=False`, achado na verificação E2E de
    12/09/2026: a coluna "Regras cadastradas" mostrava 01/11 para uma regra
    cuja 1ª aplicação de verdade, 01/10, ainda nem tinha acontecido). Só rola
    para a frente quando `data_evento` já passou, uma frequência por vez, até
    alcançar a primeira ocorrência >= hoje — mesmo critério de
    `_ocorrencias_recorrentes` (eventos_sanitarios.py), que já inclui a própria
    `data_evento` como 1ª ocorrência antes de somar a frequência."""
    d = data_evento
    guarda = 0
    while d < hoje and guarda < 3000:
        d = proxima_ocorrencia(d, frequencia_valor, frequencia_unidade)
        guarda += 1
    return d
