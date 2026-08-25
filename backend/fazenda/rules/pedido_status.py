"""
Status de Pedido — calculado a partir de ENTREGA FÍSICA, não de dinheiro
ou estoque.

## Por que este módulo existe

Hoje `Pedido.status` é uma string livre ("aberto" | "parcialmente_atendido"
| "atendido" | "cancelado") escolhida manualmente num `<select>`, ou
derivada em `pedidos.py` a partir de `PedidoItem.quantidade_atendida`/
`valor_atendido` — campos que só mudam quando um LANÇAMENTO FINANCEIRO ou
um MOVIMENTO DE ESTOQUE é vinculado ao item. Isso permite marcar um pedido
como "Atendido" sem que nada tenha, de fato, sido entregue: basta lançar a
nota ou dar entrada no estoque, o que às vezes acontece antes da mercadoria
chegar (nota antecipada, lançamento em lote no fim do mês etc.).

`calcular_status_pedido` desacopla o status desses dois módulos e passa a
derivá-lo só de `PedidoItem.quantidade_entregue` — um contador que (a partir
da próxima peça deste redesenho) só é escrito por uma ação explícita de
"marcar entrega". Esta função é PURA (sem I/O, sem consulta a banco) de
propósito: quem chama decide de onde vêm os itens (SQLModel, dict, linha de
relatório) e quando persistir o resultado — o mesmo espírito de
`fazenda.rules.parto`/`parto_resumo`.

## Nada disto está em uso ainda

Esta função existe e está testada, mas NENHUM router chama ela ainda
(pedidos.py continua usando `quantidade_atendida`/`valor_atendido` e o PUT
manual de status continua funcionando como hoje). Ligar isto ao ciclo de
vida real do Pedido é peça de uma etapa seguinte deste redesenho.
"""
from __future__ import annotations

from typing import Any

# Mesma folga usada em outras comparações de ponto flutuante do projeto:
# quantidade e quantidade_entregue chegam de contas em cascata (kg, litros,
# unidades fracionárias) e um item "completo" pode chegar como
# 2.9999999999 em vez de 3.0 por erro de arredondamento acumulado. Sem essa
# tolerância um pedido totalmente entregue ficaria preso em
# "parcialmente_atendido" para sempre.
_TOLERANCIA = 1e-9

STATUS_ABERTO = "aberto"
STATUS_PARCIALMENTE_ATENDIDO = "parcialmente_atendido"
STATUS_ATENDIDO = "atendido"
STATUS_CANCELADO = "cancelado"


def _get(item: Any, campo: str) -> Any:
    """Lê tanto de dict quanto de objeto (SQLModel `PedidoItem`) — mesmo
    helper usado em fazenda.rules.parto/perda_prenhez, pelo mesmo motivo:
    routers passam models, testes e chamadas já achatadas passam dicts."""
    if isinstance(item, dict):
        return item.get(campo)
    return getattr(item, campo, None)


def _quantidade_valida(item: Any) -> bool:
    """True quando o item tem uma `quantidade` numérica > 0 — ou seja, dá
    pra medir "quanto falta entregar". Item com quantidade None/zero é dado
    sujo (cadastro incompleto ou item só de valor, sem unidade de medida) e
    é tratado como "sempre satisfeito" por `_item_completo` — não deve travar
    o pedido inteiro em parcialmente_atendido para sempre."""
    quantidade = _get(item, "quantidade")
    return isinstance(quantidade, (int, float)) and quantidade > 0


def _item_completo(item: Any) -> bool:
    """True quando este item, sozinho, já está 100% entregue.

    Item com quantidade inválida (None/zero) conta como completo por
    definição: não há "quanto falta" a medir, então ele nunca deve ser o
    motivo de o pedido ficar preso em parcialmente_atendido — ver
    `_quantidade_valida`.
    """
    if not _quantidade_valida(item):
        return True
    quantidade = float(_get(item, "quantidade"))
    entregue = float(_get(item, "quantidade_entregue") or 0)
    return entregue >= quantidade - _TOLERANCIA


def _item_tem_entrega(item: Any) -> bool:
    """True quando já entrou QUALQUER entrega neste item (mesmo que
    parcial) — usado só para distinguir "aberto" de "parcialmente_atendido"
    quando nenhum item está completo ainda."""
    entregue = float(_get(item, "quantidade_entregue") or 0)
    return entregue > _TOLERANCIA


def calcular_status_pedido(itens: list[Any], status_atual: str) -> str:
    """Deriva o status do Pedido a partir da entrega física dos itens.

    Regras (nesta ordem):

    1. `cancelado` é terminal. Uma vez cancelado, o pedido NUNCA volta a ser
       recalculado a partir de entrega — mesmo que, depois do cancelamento,
       alguém marque itens como entregues (ex.: uma devolução registrada
       tarde, um ajuste de estoque). Isso é intencional: cancelamento é uma
       decisão explícita do usuário, não um estado que a entrega física deva
       sobrescrever silenciosamente.
    2. Sem itens, ou nenhum item com quantidade válida (>0): `aberto` — não
       há o que medir ainda.
    3. Todo item completo (ver `_item_completo`): `atendido`.
    4. Nenhum item com alguma entrega: `aberto`.
    5. Meio-termo — pelo menos um item com entrega, mas nem todos completos:
       `parcialmente_atendido`.
    """
    if status_atual == STATUS_CANCELADO:
        return STATUS_CANCELADO

    itens_mensuraveis = [item for item in itens if _quantidade_valida(item)]
    if not itens_mensuraveis:
        return STATUS_ABERTO

    if all(_item_completo(item) for item in itens_mensuraveis):
        return STATUS_ATENDIDO

    if not any(_item_tem_entrega(item) for item in itens_mensuraveis):
        return STATUS_ABERTO

    return STATUS_PARCIALMENTE_ATENDIDO
