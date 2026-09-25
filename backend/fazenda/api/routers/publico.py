"""
Páginas públicas SEM LOGIN — o fornecedor responde a uma Cotação ou confirma
um Pedido formal abrindo um link recebido por e-mail/WhatsApp, sem senha e
sem cadastro no sistema. Registrado em main.py SEM nenhuma das travas de
`exigir_modulo`/`exigir_fazenda_selecionada`/`get_current_user` que protegem
os demais routers (mesmo espírito de `POST /auth/esqueci-senha/enviar` e
`POST /auth/redefinir-senha`, que também resolvem por token, sem login).

Regra de segurança que vale para TODO endpoint deste arquivo: a fazenda
nunca vem de um parâmetro do cliente — é sempre derivada da própria linha
encontrada pelo token (`CotacaoFornecedor.fazenda_id` / `PedidoConfirmacao.
fazenda_id`). Um token de uma fazenda nunca enxerga nem altera dado de outra.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    Cotacao, CotacaoFornecedor, CotacaoItem, CotacaoResposta, Fazenda, Pedido, PedidoConfirmacao,
)
from fazenda.rules import cotacao as cotacao_rules

router = APIRouter(tags=["publico"])


def _cotacao_fornecedor_do_token(session: Session, token: str) -> CotacaoFornecedor:
    cf = session.exec(select(CotacaoFornecedor).where(CotacaoFornecedor.token_publico == token)).first()
    if not cf:
        raise HTTPException(status_code=404, detail="Link inválido ou expirado.")
    return cf


# ---------------------------------------------------------------------------
# Cotação — resposta do fornecedor
# ---------------------------------------------------------------------------
@router.get("/cotacao-publica/{token}")
def ver_cotacao_publica(token: str, session: Session = Depends(get_session)) -> dict:
    cf = _cotacao_fornecedor_do_token(session, token)
    cotacao = session.get(Cotacao, cf.cotacao_id)
    if not cotacao:
        raise HTTPException(status_code=404, detail="Link inválido ou expirado.")

    # Primeira visita marca "visualizado" — não sobrescreve se já respondeu.
    if cf.status_envio == "enviado":
        cf.status_envio = "visualizado"
        cf.visualizado_em = datetime.utcnow()
        session.add(cf)
        session.commit()

    fazenda = session.get(Fazenda, cf.fazenda_id)
    itens = session.exec(select(CotacaoItem).where(CotacaoItem.cotacao_id == cotacao.id)).all()
    respostas_existentes = {
        r.cotacao_item_id: r
        for r in session.exec(select(CotacaoResposta).where(CotacaoResposta.cotacao_fornecedor_id == cf.id)).all()
    }
    return {
        "nome_fazenda": fazenda.nome if fazenda else "",
        "numero_cotacao": cotacao.numero_cotacao,
        "categoria": cotacao.categoria,
        "prazo_resposta": cotacao.prazo_resposta,
        "status": cf.status_envio,
        "itens": [
            {
                "id": i.id, "produto": i.produto, "quantidade": i.quantidade, "unidade": i.unidade,
                "resposta": (respostas_existentes[i.id].model_dump() if i.id in respostas_existentes else None),
            }
            for i in itens
        ],
    }


class RespostaItemIn(BaseModel):
    cotacao_item_id: int
    recusado: bool = False
    preco_unitario: Optional[float] = None
    frete_incluso: Optional[bool] = None
    valor_frete: Optional[float] = None
    prazo_entrega_dias: Optional[int] = None
    condicao_pagamento: Optional[str] = None
    observacao: Optional[str] = None


@router.post("/cotacao-publica/{token}/responder")
def responder_cotacao_publica(token: str, dados: list[RespostaItemIn], session: Session = Depends(get_session)) -> dict:
    cf = _cotacao_fornecedor_do_token(session, token)
    cotacao = session.get(Cotacao, cf.cotacao_id)
    if not cotacao:
        raise HTTPException(status_code=404, detail="Link inválido ou expirado.")
    if cotacao.status in (cotacao_rules.STATUS_COMPARADA, cotacao_rules.STATUS_PEDIDOS_GERADOS, cotacao_rules.STATUS_CANCELADA):
        raise HTTPException(status_code=400, detail="Esta cotação já foi fechada — não é mais possível responder.")

    ids_itens_validos = {
        i.id for i in session.exec(select(CotacaoItem).where(CotacaoItem.cotacao_id == cotacao.id)).all()
    }
    for resp in dados:
        if resp.cotacao_item_id not in ids_itens_validos:
            raise HTTPException(status_code=400, detail="Item inválido para esta cotação.")
        existente = session.exec(
            select(CotacaoResposta).where(
                CotacaoResposta.cotacao_fornecedor_id == cf.id, CotacaoResposta.cotacao_item_id == resp.cotacao_item_id,
            )
        ).first()
        campos = dict(
            recusado=resp.recusado, preco_unitario=resp.preco_unitario, frete_incluso=resp.frete_incluso,
            valor_frete=resp.valor_frete, prazo_entrega_dias=resp.prazo_entrega_dias,
            condicao_pagamento=resp.condicao_pagamento, observacao=resp.observacao,
            atualizado_em=datetime.utcnow(),
        )
        if existente:
            for campo, valor in campos.items():
                setattr(existente, campo, valor)
            session.add(existente)
        else:
            session.add(CotacaoResposta(
                cotacao_fornecedor_id=cf.id, cotacao_item_id=resp.cotacao_item_id,
                fazenda_id=cf.fazenda_id, **campos,
            ))

    cf.status_envio = "respondido"
    cf.respondido_em = datetime.utcnow()
    session.add(cf)
    session.commit()

    # Recalcula o status de RESPOSTA da cotação (enviada -> parcial ->
    # respondida) a partir de todos os convites — nunca mexe em status
    # terminal (ver calcular_status_resposta).
    todos = session.exec(select(CotacaoFornecedor).where(CotacaoFornecedor.cotacao_id == cotacao.id)).all()
    cotacao.status = cotacao_rules.calcular_status_resposta(cotacao.status, todos)
    cotacao.atualizado_em = datetime.utcnow()
    session.add(cotacao)
    session.commit()
    return {"respondido": True}


# ---------------------------------------------------------------------------
# Pedido formal — confirmação do fornecedor
# ---------------------------------------------------------------------------
def _confirmacao_do_token(session: Session, token: str) -> PedidoConfirmacao:
    c = session.exec(select(PedidoConfirmacao).where(PedidoConfirmacao.token_publico == token)).first()
    if not c:
        raise HTTPException(status_code=404, detail="Link inválido ou expirado.")
    return c


@router.get("/pedido-confirmacao-publica/{token}")
def ver_pedido_confirmacao_publica(token: str, session: Session = Depends(get_session)) -> dict:
    confirmacao = _confirmacao_do_token(session, token)
    pedido = session.get(Pedido, confirmacao.pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Link inválido ou expirado.")
    fazenda = session.get(Fazenda, confirmacao.fazenda_id)

    from fazenda.models import PedidoItem  # import local: evita import não usado em outros endpoints deste arquivo
    itens = session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido.id)).all()

    return {
        "numero_pedido": pedido.numero_pedido,
        "status": confirmacao.status,
        "itens": [
            {"produto": i.produto_servico, "quantidade": i.quantidade, "valor_total_estimado": i.valor_total_estimado}
            for i in itens
        ],
        "fazenda": {
            "nome": fazenda.nome if fazenda else "",
            "tipo_documento": fazenda.tipo_documento if fazenda else None,
            "documento": fazenda.documento if fazenda else None,
            "inscricao_estadual": fazenda.inscricao_estadual if fazenda else None,
            "endereco": fazenda.endereco if fazenda else None,
            "telefone": fazenda.telefone if fazenda else None,
            "email": fazenda.email if fazenda else None,
        } if fazenda else None,
    }


class ConfirmarPedidoIn(BaseModel):
    previsao_entrega: Optional[str] = None
    observacao: Optional[str] = None
    recusado: bool = False


@router.post("/pedido-confirmacao-publica/{token}/confirmar")
def confirmar_pedido_publico(token: str, dados: ConfirmarPedidoIn, session: Session = Depends(get_session)) -> dict:
    confirmacao = _confirmacao_do_token(session, token)
    if confirmacao.status != "enviado":
        raise HTTPException(status_code=400, detail="Este pedido já foi respondido.")
    confirmacao.status = "recusado" if dados.recusado else "confirmado"
    confirmacao.previsao_entrega = dados.previsao_entrega
    confirmacao.observacao_fornecedor = dados.observacao
    confirmacao.confirmado_em = datetime.utcnow()
    session.add(confirmacao)
    session.commit()
    return {"status": confirmacao.status}
