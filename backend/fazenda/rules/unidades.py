"""
Compatibilidade entre unidades de aplicação e a unidade de estoque de um
produto — evita, por exemplo, aplicar em "litros" um produto cujo estoque é
contado em "ml"/"unidade" (ex.: Borgal 50ml pode ser aplicado em ml ou em
unidade, mas não em litros).
"""
from __future__ import annotations

# Densidade do leite cru a 15 °C — 1 litro ≈ 1,029 kg. O controle leiteiro é
# lançado em kg e a entrega ao laticínio pode ser contratada em litro ou em
# kg; sem converter, o litro entra na conta como se fosse kg e o balanço
# Controle × Entregue superestima o "não entregue" (leite dos bezerros e da
# equipe) em ~2,9% do volume entregue.
DENSIDADE_LEITE_KG_POR_L = 1.029

UNIDADES_ENTREGA_LEITE = ("kg", "L")


def leite_para_kg(quantidade: float, unidade: str | None) -> float:
    """Converte um volume de leite para kg. `unidade` ausente ou desconhecida
    é tratada como kg — é o padrão do sistema e o que os lançamentos antigos
    (anteriores ao campo `unidade`) representam."""
    if (unidade or "kg").strip().upper() == "L":
        return quantidade * DENSIDADE_LEITE_KG_POR_L
    return quantidade


# Grupos de unidades intercompatíveis para fins de SELEÇÃO na aplicação.
GRUPOS_UNIDADE: list[set[str]] = [
    {"ml", "unidade", "dose"},
    {"L", "kg", "saca 30kg", "saca 60kg"},
]

# Sinônimos/abreviações legadas (import de planilha, cadastro antigo) que
# precisam cair no mesmo grupo do valor canônico — senão o item some das
# opções de unidade compatível (ex.: "un" não batia com "unidade" e escondia "ml").
_SINONIMOS_UNIDADE = {"un": "unidade", "und": "unidade", "unid": "unidade", "unidades": "unidade"}


def unidades_compativeis(unidade_estoque: str | None) -> list[str]:
    """Unidades que fazem sentido escolher na aplicação, dado o produto guardar estoque em `unidade_estoque`."""
    if not unidade_estoque:
        return ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"]
    normalizada = _SINONIMOS_UNIDADE.get(unidade_estoque.strip().lower(), unidade_estoque)
    for grupo in GRUPOS_UNIDADE:
        if normalizada in grupo:
            return sorted(grupo)
    return [unidade_estoque]


def pode_dar_baixa_direta(unidade_aplicacao: str, unidade_estoque: str | None) -> bool:
    """
    Só é seguro debitar diretamente do estoque quando a unidade da aplicação é
    exatamente a mesma do estoque — não há fator de conversão cadastrado
    entre unidades do mesmo grupo (ex.: quantos ml tem 1 "unidade").
    """
    return bool(unidade_estoque) and unidade_aplicacao == unidade_estoque
