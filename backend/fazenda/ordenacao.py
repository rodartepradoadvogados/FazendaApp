"""Chave de ordenação numérica para campos que guardam número como texto."""
from __future__ import annotations


def chave_numero(valor: str | None) -> tuple:
    """
    Ordena números guardados como string em ordem crescente de verdade — "10"
    depois de "9", não antes (comparação lexicográfica erraria isso). Valores
    não puramente numéricos (ex.: tatuagem/código com letras) vão depois dos
    numéricos, em ordem alfabética entre si.
    """
    texto = (valor or "").strip()
    if texto.isdigit():
        return (0, int(texto), "")
    return (1, 0, texto)
