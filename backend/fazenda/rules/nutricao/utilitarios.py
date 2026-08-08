"""Utilitários numéricos compartilhados pelo motor de formulação de dietas.

Toda divisão feita em qualquer módulo de `fazenda.rules.nutricao` deve passar
por `divisao_segura` — é a única forma de garantir que nenhum `ZeroDivisionError`,
`nan` ou `inf` escape de `avaliar_dieta`.
"""
from __future__ import annotations

import math
from typing import Optional

_EPSILON = 1e-9


def divisao_segura(
    numerador: Optional[float],
    denominador: Optional[float],
    quando_zero: Optional[float] = 0.0,
) -> Optional[float]:
    """Retorna `numerador / denominador`.

    Se `denominador` for `None`, zero, ou tiver valor absoluto menor que
    1e-9, devolve `quando_zero` em vez de propagar `ZeroDivisionError`,
    `nan` ou `inf`. `quando_zero` pode ser `None` — usado nos poucos casos em
    que a grandeza resultante é genuinamente indefinida (ex.: dias para
    variar 1 ponto de ECC quando não há ganho-alvo nenhum).

    Também protege contra `numerador`/`denominador` ausentes (`None`) e
    contra resultados que dariam `nan`/`inf` por outros motivos numéricos.
    """
    if numerador is None or denominador is None:
        return quando_zero
    if abs(denominador) < _EPSILON:
        return quando_zero
    resultado = numerador / denominador
    if math.isnan(resultado) or math.isinf(resultado):
        return quando_zero
    return resultado


def piso(valor: Optional[float], minimo: float) -> float:
    """Aplica um piso (mínimo) a `valor`, tratando `None` como 0.0 antes de
    comparar — usado para truncar grandezas que nunca podem ficar negativas
    ou abaixo de um mínimo biológico (ex.: nitrogênio microbiano, 10 g/d)."""
    v = 0.0 if valor is None else valor
    return minimo if v < minimo else v


def teto(valor: Optional[float], maximo: float) -> float:
    """Aplica um teto (máximo) a `valor`, tratando `None` como 0.0 antes de
    comparar — usado para truncar eficiências e frações que não podem
    superar 100% (ex.: eficiência de uso de PDR pela microbiota)."""
    v = 0.0 if valor is None else valor
    return maximo if v > maximo else v


def limitar(valor: Optional[float], minimo: float, maximo: float) -> float:
    """Restringe `valor` ao intervalo fechado [minimo, maximo]."""
    v = 0.0 if valor is None else valor
    if v < minimo:
        return minimo
    if v > maximo:
        return maximo
    return v


def numero_finito(valor: Optional[float]) -> bool:
    """True se `valor` não for `None` e for um float finito (não nan/inf)."""
    if valor is None:
        return False
    try:
        return math.isfinite(valor)
    except TypeError:
        return False
