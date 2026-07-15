"""
Depreciação do patrimônio — linha reta (linear), a partir da vida útil
cadastrada (texto livre, ex. "7 Anos" ou "60 Meses"), da data de imobilização
e do valor residual. Quando a vida útil não pode ser interpretada (ou falta a
data de imobilização), o item entra na resposta sem depreciação e com um
aviso — não trava o cálculo dos demais itens.
"""
from __future__ import annotations

import re
from datetime import date


def _vida_util_em_anos(texto: str | None) -> float | None:
    if not texto:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", texto)
    if not m:
        return None
    valor = float(m.group(1).replace(",", "."))
    return valor / 12 if re.search(r"m[eê]s", texto, re.IGNORECASE) else valor


def calcular_depreciacao(item: dict, hoje: date | None = None) -> dict:
    """Recebe um dict com os campos do Patrimonio (model_dump()) e devolve
    depreciacao_acumulada, valor_atual, vida_util_anos e uma eventual
    inconsistência (vida útil não reconhecida ou sem data de imobilização)."""
    hoje = hoje or date.today()
    valor_total = item.get("valor_total") or 0.0
    valor_residual = item.get("valor_residual") or 0.0
    data_imob = item.get("data_imobilizacao")
    vida_util_anos = _vida_util_em_anos(item.get("vida_util"))

    if item.get("data_baixa"):
        # Já baixado — parou de depreciar; o valor atual é o residual cadastrado.
        return {
            "depreciacao_acumulada": round(max(valor_total - valor_residual, 0.0), 2),
            "valor_atual": round(valor_residual, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": None,
        }
    if not data_imob:
        return {
            "depreciacao_acumulada": None, "valor_atual": round(valor_total, 2),
            "vida_util_anos": vida_util_anos,
            "inconsistencia": "Sem data de imobilização — não é possível calcular a depreciação.",
        }
    if not vida_util_anos or vida_util_anos <= 0:
        return {
            "depreciacao_acumulada": None, "valor_atual": round(valor_total, 2),
            "vida_util_anos": None,
            "inconsistencia": f'Vida útil "{item.get("vida_util") or "—"}" não reconhecida — cadastre um número (ex.: "7 anos").',
        }

    idade_anos = max((hoje - data_imob).days / 365.25, 0.0)
    depreciavel = max(valor_total - valor_residual, 0.0)
    dep_anual = depreciavel / vida_util_anos
    acumulada = min(dep_anual * idade_anos, depreciavel)
    return {
        "depreciacao_acumulada": round(acumulada, 2),
        "valor_atual": round(valor_total - acumulada, 2),
        "vida_util_anos": vida_util_anos,
        "inconsistencia": None,
    }
