"""
Conversão de unidade para quilos — dona única desta regra.

Existe porque o rateio da sobra por alimento precisa somar itens de uma dieta
que estão em unidades diferentes, e até aqui cada lugar resolvia isso por conta
própria, sempre da mesma forma incompleta: `vagao_kg_dia`
(`routers/alimentacao.py`) soma apenas `unidade in ("kg","g")`, e o frontend
repete o mesmo filtro. O efeito é que "saca 30kg" — que traz o fator de
conversão literalmente escrito no nome — fica fora de qualquer total em quilos,
como se não fosse massa.

O ponto delicado é o retorno `None`, e ele é deliberado. Litro, dose e unidade
NÃO têm conversão possível para massa sem densidade ou sem saber o que é uma
"dose" daquele produto. Devolver 0.0 nesses casos seria pior que não responder:
um zero soma silenciosamente no denominador e faz o percentual de sobra sair
menor do que é, o que mandaria o alerta na direção errada — reduzir quando
deveria acrescentar. Quem chama tem de decidir o que fazer com `None`, e a
regra do produto é declará-lo na tela ("estes itens ficaram fora do rateio")
em vez de escondê-lo numa conta.
"""
from __future__ import annotations

# Fatores para quilos. As sacas são as unidades comerciais usadas no cadastro
# de dietas (ver UNIDADES em CadastroAlimentacao.tsx) e o peso está no próprio
# rótulo — não há ambiguidade a resolver, só a conversão a aplicar.
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

# Unidades reconhecidas para as quais a conversão é IMPOSSÍVEL, não apenas
# desconhecida. Separadas das demais para que `kg_equivalente` devolva None
# tanto para estas quanto para um texto que ninguém previu — em ambos os casos
# a resposta honesta é "não sei", e o chamador trata igual.
UNIDADES_SEM_MASSA: frozenset[str] = frozenset(
    {"l", "litro", "litros", "ml", "dose", "doses", "unidade", "unidades", "un"}
)


def kg_equivalente(quantidade: float | None, unidade: str | None) -> float | None:
    """Quantidade convertida para quilos, ou `None` quando a unidade não tem
    conversão possível para massa.

    `None` é resposta legítima e precisa ser tratada por quem chama — nunca
    substituída por zero (ver o docstring do módulo)."""
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
