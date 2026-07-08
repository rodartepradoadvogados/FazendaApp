"""
Compatibilidade entre unidades de aplicação e a unidade de estoque de um
produto — evita, por exemplo, aplicar em "litros" um produto cujo estoque é
contado em "ml"/"unidade" (ex.: Borgal 50ml pode ser aplicado em ml ou em
unidade, mas não em litros).
"""
from __future__ import annotations

# Grupos de unidades intercompatíveis para fins de SELEÇÃO na aplicação.
GRUPOS_UNIDADE: list[set[str]] = [
    {"ml", "unidade", "dose"},
    {"L", "kg"},
]


def unidades_compativeis(unidade_estoque: str | None) -> list[str]:
    """Unidades que fazem sentido escolher na aplicação, dado o produto guardar estoque em `unidade_estoque`."""
    if not unidade_estoque:
        return ["ml", "L", "unidade", "dose", "kg"]
    for grupo in GRUPOS_UNIDADE:
        if unidade_estoque in grupo:
            return sorted(grupo)
    return [unidade_estoque]


def pode_dar_baixa_direta(unidade_aplicacao: str, unidade_estoque: str | None) -> bool:
    """
    Só é seguro debitar diretamente do estoque quando a unidade da aplicação é
    exatamente a mesma do estoque — não há fator de conversão cadastrado
    entre unidades do mesmo grupo (ex.: quantos ml tem 1 "unidade").
    """
    return bool(unidade_estoque) and unidade_aplicacao == unidade_estoque
