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


def leite_em_litros(quantidade: float, unidade: str | None) -> float:
    """Volume de leite em LITROS de verdade, qualquer que seja a unidade em
    que a entrega foi lançada (`kg`, o padrão, ou `L`). Helper ÚNICO dos
    relatórios que dividem por litro (RMCA, custo por litro, futuro COE/L):
    ninguém divide por `EntregaLeiteMensal.quantidade_litros` cru — o nome do
    campo é histórico, ele guarda o número na unidade escolhida (Fase A, PR 4).

    Mesma conta que o RMCA já fazia (`leite_para_kg(q, u) / densidade`), de
    propósito: o número do RMCA não muda ao passar por aqui."""
    return leite_para_kg(quantidade, unidade) / DENSIDADE_LEITE_KG_POR_L


_SINONIMOS_LEITE_L = frozenset({"l", "lt", "lts", "litro", "litros"})
_SINONIMOS_LEITE_KG = frozenset({"kg", "kgs", "quilo", "quilos", "quilograma", "quilogramas"})


def unidade_leite_canonica(unidade: str | None) -> str | None:
    """`"L"` ou `"kg"` quando o texto da unidade (`Estoque.unidade`, livre) é
    inequivocamente litro ou quilo; `None` para vazio ou qualquer outra coisa
    (saca, dose, ml…). DIFERENTE de `leite_para_kg`/`leite_em_litros`, que tratam
    unidade ausente como kg (o padrão histórico da Venda mensal): aqui a unidade
    da NOTA nunca é chutada — `None` quer dizer "não sei", e quem chama avisa em
    vez de converter."""
    u = (unidade or "").strip().lower().rstrip(".")
    if u in _SINONIMOS_LEITE_L:
        return "L"
    if u in _SINONIMOS_LEITE_KG:
        return "kg"
    return None


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
    return bool(unidade_estoque) and unidades_iguais(unidade_aplicacao, unidade_estoque)


def unidades_iguais(a: str | None, b: str | None) -> bool:
    """Mesma unidade, ignorando caixa/espacos e os sinonimos legados (un = unidade). NUNCA converte."""
    def _n(u: str | None) -> str:
        u = (u or "").strip().lower()
        return _SINONIMOS_UNIDADE.get(u, u)
    return bool(_n(a)) and _n(a) == _n(b)


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


def de_kg_para_unidade(kg: float | None, unidade: str | None) -> float | None:
    """Inverso de `kg_equivalente` — quantos `unidade` equivalem a `kg`
    quilos. Usada pelo lançamento de consumo "kg do vagão" (Lançamentos >
    Alimentação): o total do vagão é repartido pela dieta EM QUILOS, mas cada
    `ConsumoAlimento` precisa ser gravado na unidade do próprio item — é ela
    que casa, byte a byte, com `Estoque.unidade` em `pode_dar_baixa_direta`
    (só compara igualdade exata, sem equivalência entre unidades). `None`
    nas mesmas condições de `kg_equivalente` (unidade sem conversão)."""
    if kg is None:
        return None
    fator = _FATORES_KG.get((unidade or "").strip().lower())
    if not fator:
        return None
    return float(kg) / fator
