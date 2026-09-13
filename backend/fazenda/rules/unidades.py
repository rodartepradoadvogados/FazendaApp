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


# ---------------------------------------------------------------------------
# Conversão para QUILOS — usada pelo rateio da sobra de cocho por alimento.
# ---------------------------------------------------------------------------
# Existe porque cada lugar resolvia isso por conta própria, sempre da mesma
# forma incompleta: `vagao_kg_dia` (routers/alimentacao.py) soma apenas
# `unidade in ("kg","g")`, e o frontend repete o mesmo filtro. O efeito é que
# "saca 30kg" — que traz o fator de conversão literalmente escrito no nome —
# fica fora de todo total em quilos, como se não fosse massa.
#
# O ponto delicado é o retorno `None`, e ele é deliberado. Litro, dose e
# unidade NÃO têm conversão para massa sem densidade ou sem saber o que é uma
# "dose" daquele produto. Devolver 0.0 seria pior que não responder: o zero
# soma em silêncio no denominador do percentual de sobra, a sobra parece
# proporcionalmente MAIOR do que é, e o alerta manda REDUZIR o trato de um lote
# que na verdade está comendo tudo. Quem chama tem de tratar o `None` — e a
# regra do produto é declará-lo na tela ("estes itens ficaram fora do rateio")
# em vez de escondê-lo numa conta.
_FATORES_KG: dict[str, float] = {
    "kg": 1.0,
    "quilo": 1.0,
    "quilos": 1.0,
    "g": 0.001,
    "grama": 0.001,
    "gramas": 0.001,
    "saca 30kg": 30.0,
    "saca 60kg": 60.0,
}

# Unidades para as quais a conversão é IMPOSSÍVEL, não apenas desconhecida.
# Separadas para deixar a intenção explícita — mas `kg_equivalente` devolve
# None tanto para estas quanto para um texto que ninguém previu: em ambos os
# casos a resposta honesta é "não sei", e o chamador trata igual.
UNIDADES_SEM_MASSA: frozenset[str] = frozenset(
    {"l", "litro", "litros", "ml", "dose", "doses", "unidade", "unidades", "un"}
)


def kg_equivalente(quantidade: float | None, unidade: str | None) -> float | None:
    """Quantidade convertida para quilos, ou `None` quando a unidade não tem
    conversão possível para massa.

    `None` é resposta legítima e precisa ser tratada por quem chama — nunca
    substituída por zero (ver o comentário acima)."""
    if quantidade is None:
        return None
    fator = _FATORES_KG.get((unidade or "").strip().lower())
    if fator is None:
        return None
    return float(quantidade) * fator


def converte_para_kg(unidade: str | None) -> bool:
    """Se a unidade tem conversão para quilos. Serve às telas, que precisam
    marcar o item ANTES de haver quantidade lançada."""
    return (unidade or "").strip().lower() in _FATORES_KG
