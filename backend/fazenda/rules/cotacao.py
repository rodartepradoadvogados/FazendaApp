"""
Regras da Cotação de Preços com Fornecedores.

`calcular_status_resposta` é pura (mesmo espírito de
`rules.pedido_status.calcular_status_pedido`) — deriva o status de resposta
da cotação a partir da lista de convites (`CotacaoFornecedor`), sem tocar
nos status terminais (comparada/pedidos_gerados/expirada/cancelada), que só
uma ação explícita do gestor muda.

`gerar_pedidos_da_cotacao` cria os Pedidos de verdade a partir dos vencedores
marcados na Comparação — reaproveita a numeração e o padrão de `origem_tipo`
já usados por `planejamento.py::importar_para_pedido` (mesmo precedente de
"pedido nascido de outra tela"), inclusive o mesmo import cruzado de
`_proximo_numero_pedido` do router de Pedidos.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlmodel import Session, select

from fazenda.api.routers.pedidos import _proximo_numero_pedido
from fazenda.models import Cotacao, CotacaoFornecedor, CotacaoItem, CotacaoResposta, Fornecedor, Pedido, PedidoItem

STATUS_RASCUNHO = "rascunho"
STATUS_ENVIADA = "enviada"
STATUS_PARCIALMENTE_RESPONDIDA = "parcialmente_respondida"
STATUS_RESPONDIDA = "respondida"
STATUS_COMPARADA = "comparada"
STATUS_PEDIDOS_GERADOS = "pedidos_gerados"
STATUS_EXPIRADA = "expirada"
STATUS_CANCELADA = "cancelada"

# Status que só mudam por ação explícita do gestor (Comparar/Gerar pedidos/
# Cancelar) — nunca recalculados a partir de quantas respostas chegaram.
STATUS_TERMINAIS_MANUAIS = {STATUS_COMPARADA, STATUS_PEDIDOS_GERADOS, STATUS_EXPIRADA, STATUS_CANCELADA}

_RESPONDIDOS = {"respondido", "recusado"}


def _status_envio(f: Any) -> str | None:
    return f.get("status_envio") if isinstance(f, dict) else getattr(f, "status_envio", None)


def calcular_status_resposta(status_atual: str, fornecedores: list[Any]) -> str:
    """Deriva enviada/parcialmente_respondida/respondida a partir dos
    convites — chame depois de qualquer mudança em `CotacaoFornecedor.
    status_envio` (marcar visualizado, registrar resposta). Não mexe em
    status terminais: uma cotação já comparada/com pedidos gerados/expirada/
    cancelada nunca volta pra trás por causa de uma resposta atrasada."""
    if status_atual in STATUS_TERMINAIS_MANUAIS:
        return status_atual
    if not fornecedores:
        return STATUS_RASCUNHO
    respondidos = sum(1 for f in fornecedores if _status_envio(f) in _RESPONDIDOS)
    if respondidos == 0:
        return STATUS_ENVIADA
    if respondidos < len(fornecedores):
        return STATUS_PARCIALMENTE_RESPONDIDA
    return STATUS_RESPONDIDA


def montar_mensagem_cotacao(nome_fazenda: str, link: str) -> str:
    """Texto padrão sugerido no disparo — o gestor pode editar livremente
    antes de enviar (ver frontend: seletor link/texto padrão/texto livre)."""
    return f"Olá! A {nome_fazenda} tem uma nova cotação de preços para você. Responda pelo link, sem precisar de login: {link}"


def montar_mensagem_pedido_formal(nome_fazenda: str, numero_pedido: str, link: str) -> str:
    return (
        f"Olá! A {nome_fazenda} confirmou o pedido {numero_pedido} com sua empresa. "
        f"Confirme o recebimento e a previsão de entrega pelo link: {link}"
    )


def gerar_pedidos_da_cotacao(
    session: Session, *, cotacao: Cotacao, fazenda_id: int | None, usuario_id: int | None,
) -> list[Pedido]:
    """Um Pedido (tipo="compra") por fornecedor vencedor de ao menos um item,
    com um PedidoItem por item vencido daquele fornecedor. Não mexe em
    Estoque nem Financeiro — os Pedidos nascem "abertos", como qualquer
    Pedido criado à mão; dali em diante seguem o motor de sempre (marcar
    entrega, lançar pagamento)."""
    respostas_vencedoras = session.exec(
        select(CotacaoResposta)
        .join(CotacaoFornecedor, CotacaoResposta.cotacao_fornecedor_id == CotacaoFornecedor.id)
        .where(CotacaoFornecedor.cotacao_id == cotacao.id, CotacaoResposta.vencedor == True)  # noqa: E712
    ).all()

    por_fornecedor: dict[int, list[CotacaoResposta]] = {}
    fornecedor_por_resposta: dict[int, int] = {}
    for resp in respostas_vencedoras:
        cf = session.get(CotacaoFornecedor, resp.cotacao_fornecedor_id)
        if cf is None or (fazenda_id is not None and cf.fazenda_id != fazenda_id):
            continue
        por_fornecedor.setdefault(cf.fornecedor_id, []).append(resp)
        fornecedor_por_resposta[resp.id] = cf.fornecedor_id

    pedidos_criados: list[Pedido] = []
    for fornecedor_id, respostas in por_fornecedor.items():
        fornecedor = session.get(Fornecedor, fornecedor_id)
        if fornecedor is None:
            continue
        numero_pedido = _proximo_numero_pedido(session, date.today().year, fazenda_id)
        pedido = Pedido(
            numero_pedido=numero_pedido, tipo="compra", fornecedor_cliente=fornecedor.nome,
            data_pedido=date.today(),
            observacao=f"Gerado da Cotação {cotacao.numero_cotacao}",
            origem_tipo="cotacao", origem_item_id=cotacao.id,
            usuario_id=usuario_id, fazenda_id=fazenda_id,
        )
        session.add(pedido)
        session.commit()
        session.refresh(pedido)

        for resp in respostas:
            item = session.get(CotacaoItem, resp.cotacao_item_id)
            if item is None:
                continue
            valor_unitario = resp.preco_unitario or 0.0
            session.add(PedidoItem(
                pedido_id=pedido.id, tipo_item="produto", produto_servico=item.produto,
                quantidade=item.quantidade, valor_unitario_estimado=valor_unitario,
                valor_total_estimado=round(valor_unitario * item.quantidade, 2),
                fazenda_id=fazenda_id,
            ))
        session.commit()
        pedidos_criados.append(pedido)

    return pedidos_criados
