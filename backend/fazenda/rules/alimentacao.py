"""
Alimentação — cruza o plano de dieta (por cabeça/dia) com o efetivo de cada lote
para estimar o consumo diário total de cada ingrediente.

Lote N (DIETA) ↔ grupo cujo código de 2 dígitos é N (ex.: lote 1 ↔ '01 - NOV. ALTA').
"""
from __future__ import annotations

from typing import Optional


def _codigo_grupo(grupo: Optional[str]) -> Optional[str]:
    if not grupo:
        return None
    g = grupo.strip()
    return g[:2] if len(g) >= 2 and g[:2].isdigit() else None


def _efetivo_por_lote(animais: list[dict]) -> dict[int, int]:
    """Conta animais ativos por código de lote (1..14)."""
    contagem: dict[int, int] = {}
    for a in animais:
        cod = _codigo_grupo(a.get("grupo_primario"))
        if cod:
            n = int(cod)
            contagem[n] = contagem.get(n, 0) + 1
    return contagem


def calcular_consumo(dietas: list[dict], animais: list[dict]) -> dict:
    """
    Retorna:
      - por_lote: plano de cada lote com efetivo e consumo do lote por ingrediente
      - consumo_total: soma por ingrediente (kg ou L/dia) no rebanho inteiro
    """
    efetivo = _efetivo_por_lote(animais)

    # Agrupa dietas por lote
    lotes: dict[int, dict] = {}
    for d in dietas:
        lote = d.get("lote")
        if lote is None:
            continue
        info = lotes.setdefault(lote, {"lote": lote, "categoria": d.get("categoria"), "ingredientes": []})
        info["ingredientes"].append({
            "ingrediente": d.get("ingrediente"),
            "por_cabeca": d.get("quantidade"),
            "unidade": d.get("unidade"),
        })

    consumo_total: dict[str, dict] = {}
    por_lote = []
    for lote in sorted(lotes):
        info = lotes[lote]
        n = efetivo.get(lote, 0)
        itens = []
        for ing in info["ingredientes"]:
            por_cab = ing["por_cabeca"] or 0
            total = round(por_cab * n, 2)
            itens.append({**ing, "efetivo": n, "consumo_dia": total})
            chave = ing["ingrediente"]
            acc = consumo_total.setdefault(chave, {"ingrediente": chave, "unidade": ing["unidade"], "consumo_dia": 0.0})
            acc["consumo_dia"] = round(acc["consumo_dia"] + total, 2)
        por_lote.append({
            "lote": lote,
            "categoria": info["categoria"],
            "efetivo": n,
            "itens": itens,
        })

    return {
        "por_lote": por_lote,
        "consumo_total": sorted(consumo_total.values(), key=lambda x: -x["consumo_dia"]),
    }
