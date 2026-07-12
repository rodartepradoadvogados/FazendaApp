"""
Agendamento de pesagem do rebanho — gera as datas de pesagem (por fase) que
caem numa janela da Agenda, respeitando a periodicidade e o dia da semana fixo
(ex.: de 15 em 15 dias, às terças-feiras).
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.calendario_sanitario import proxima_ocorrencia


def _snap_dia_semana(d: date, dia_semana: int) -> date:
    """Move a data para o dia da semana mais próximo (0=segunda … 6=domingo)."""
    delta = (dia_semana - d.weekday()) % 7
    if delta > 3:
        delta -= 7
    return d + timedelta(days=delta)


def ocorrencias_pesagem(
    data_referencia: date, frequencia_valor: int, frequencia_unidade: str,
    dia_semana: int, ini: date, fim: date, limite: int = 500,
) -> list[date]:
    """Datas de pesagem (ancoradas no dia da semana) dentro de [ini, fim].

    Parte da data de referência e avança pela periodicidade, encaixando cada
    ocorrência no dia da semana configurado — assim "15 em 15 dias, às terças"
    vira a terça mais próxima de cada marco quinzenal."""
    if frequencia_valor <= 0:
        return []
    atual = _snap_dia_semana(data_referencia, dia_semana)
    datas: list[date] = []
    # Recua até antes do início da janela para não perder ocorrências.
    guard = 0
    while atual > ini and guard < limite:
        # anda um passo para trás
        anterior = proxima_ocorrencia(atual, -frequencia_valor, frequencia_unidade) \
            if frequencia_unidade == "dias" else atual - timedelta(days=frequencia_valor * 30)
        anterior = _snap_dia_semana(anterior, dia_semana)
        if anterior >= atual:
            break
        atual = anterior
        guard += 1
    guard = 0
    while atual <= fim and guard < limite:
        if atual >= ini:
            datas.append(atual)
        prox = proxima_ocorrencia(atual, frequencia_valor, frequencia_unidade)
        prox = _snap_dia_semana(prox, dia_semana)
        if prox <= atual:
            prox = atual + timedelta(days=max(1, frequencia_valor))
        atual = prox
        guard += 1
    return datas


def idade_dias(data_nasc: date | None, ref: date) -> int | None:
    if not data_nasc:
        return None
    return (ref - data_nasc).days
