"""
Pilar Reprodução do Dossiê de Recria.

Duas análises, sobre os dados que a fazenda já lança (Parto + Serviço):
 - Wisconsin: estatística da IDADE AO 1º PARTO — média, mínima, máxima, desvio,
   assimetria e curtose (mede a uniformidade e a "cauda" de novilhas tardias),
   distribuição e o CUSTO DE RECRIA EXCEDENTE em R$.
 - Taxa de Prenhez em ciclos de 21 dias (método DairyComp): por ciclo,
   Taxa de Serviço × Taxa de Concepção = Taxa de Prenhez.

Puro Python, testável e isolado de banco.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

DIAS_MES = 30.44


def estatisticas_idade_parto(idades_meses: list[float]) -> dict | None:
    """Estatística descritiva da idade ao 1º parto (em meses)."""
    xs = [x for x in idades_meses if x is not None and x > 0]
    n = len(xs)
    if n == 0:
        return None
    media = sum(xs) / n
    minimo, maximo = min(xs), max(xs)
    variancia = sum((x - media) ** 2 for x in xs) / n
    desvio = math.sqrt(variancia)
    # Assimetria e curtose (Fisher-Pearson populacional).
    if desvio > 0 and n > 2:
        assimetria = (sum((x - media) ** 3 for x in xs) / n) / (desvio ** 3)
        curtose = (sum((x - media) ** 4 for x in xs) / n) / (desvio ** 4) - 3.0
    else:
        assimetria = 0.0
        curtose = 0.0
    ordenado = sorted(xs)

    def pct(p: float) -> float:
        if n == 1:
            return ordenado[0]
        i = p * (n - 1)
        lo = int(math.floor(i))
        frac = i - lo
        hi = min(lo + 1, n - 1)
        return ordenado[lo] + frac * (ordenado[hi] - ordenado[lo])

    p_novo, p_velho = pct(0.05), pct(0.95)
    return {
        "n": n,
        "media": round(media, 1),
        "minimo": round(minimo, 1),
        "maximo": round(maximo, 1),
        "desvio_padrao": round(desvio, 2),
        "assimetria": round(assimetria, 2),
        "curtose": round(curtose, 2),
        "idade_tipica_min": round(p_novo, 1),
        "idade_tipica_max": round(p_velho, 1),
        "amplitude_tipica": round(p_velho - p_novo, 1),
    }


def distribuicao_idade_parto(idades_meses: list[float], mn: int = 19, mx: int = 35) -> list[dict]:
    """Histograma por mês inteiro (% de novilhas em cada mês de idade ao parto)."""
    xs = [x for x in idades_meses if x is not None and x > 0]
    if not xs:
        return []
    cont: dict[int, int] = {}
    for x in xs:
        m = int(round(x))
        m = max(mn, min(mx, m))
        cont[m] = cont.get(m, 0) + 1
    total = len(xs)
    return [{"mes": m, "n": cont.get(m, 0), "pct": round(100 * cont.get(m, 0) / total, 1)} for m in range(mn, mx + 1)]


def custo_recria_excedente(idades_meses: list[float], meta_meses: float, custo_diario: float) -> dict:
    """Dias e R$ de recria além da meta, por rebanho (soma) e por novilha (média)."""
    xs = [x for x in idades_meses if x is not None and x > 0]
    if not xs:
        return {"n": 0, "dias_excedentes_total": 0, "custo_total": 0.0, "dias_por_novilha": 0.0, "custo_por_novilha": 0.0}
    dias = [max(0.0, (x - meta_meses) * DIAS_MES) for x in xs]
    dias_total = sum(dias)
    custo_total = dias_total * custo_diario
    n = len(xs)
    return {
        "n": n,
        "dias_excedentes_total": round(dias_total),
        "custo_total": round(custo_total, 2),
        "dias_por_novilha": round(dias_total / n, 1),
        "custo_por_novilha": round(custo_total / n, 2),
    }

