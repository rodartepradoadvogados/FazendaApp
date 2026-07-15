"""
Router de Pedidos — intenção de compra/venda que, por si só, NÃO gera
movimentação de estoque nem lançamento financeiro. Só passa a refletir em
Financeiro (ver `financeiro.py::criar_lancamento`, campo `pedido_id`) e em
Estoque (ver `estoque.py::_criar_movimento_estoque`, campos `pedido_id`/
`pedido_item_id`) quando uma nota fiscal/recibo ou uma entrada física é
lançada e vinculada a este pedido.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import (
    ContaGerencial, Fornecedor, MovimentoEstoque, Pedido, PedidoItem, ServicoCadastro, Usuario,
)
from fazenda.rules.centro_custo import mapear_centro_custo

router = APIRouter(prefix="/pedidos", tags=["pedidos"])


def _proximo_numero_pedido(session: Session, ano: int) -> str:
    prefixo = f"PED-{ano}-"
    existentes = session.exec(
        select(Pedido.numero_pedido).where(Pedido.numero_pedido.like(f"{prefixo}%"))
    ).all()
    maior = 0
    for n in existentes:
        if n and n.startswith(prefixo):
            try:
                maior = max(maior, int(n[len(prefixo):]))
            except ValueError:
                continue
    return f"{prefixo}{maior + 1:05d}"


class PedidoItemIn(BaseModel):
    tipo_item: str  # "produto" | "servico"
    produto_servico: str
    codigo_conta_gerencial: Optional[str] = None
    nome_conta_gerencial: Optional[str] = None
    quantidade: Optional[float] = None
    valor_unitario_estimado: Optional[float] = None
    valor_total_estimado: float


class PedidoIn(BaseModel):
    tipo: str  # "compra" | "venda"
    fornecedor_cliente: Optional[str] = None
    centro_custo: Optional[str] = None
    data_pedido: date
    data_prevista: Optional[date] = None
    observacao: Optional[str] = None
    responsavel: Optional[str] = None
    itens: list[PedidoItemIn]
    origem_tipo: Optional[str] = None
    origem_item_id: Optional[int] = None


def _recalcular_status(session: Session, pedido: Pedido) -> None:
    """Recalcula o status do pedido a partir do quanto já foi atendido pelos
    itens (por sua vez atualizados quando um lançamento financeiro ou um
    movimento de estoque é vinculado a este pedido)."""
    itens = session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido.id)).all()
    if not itens:
        return
    total_estimado = sum(i.valor_total_estimado for i in itens)
    total_atendido = sum(i.valor_atendido for i in itens)
    if pedido.status == "cancelado":
        return
    if total_atendido <= 0:
        pedido.status = "aberto"
    elif total_atendido >= total_estimado:
        pedido.status = "atendido"
    else:
        pedido.status = "parcialmente_atendido"
    pedido.atualizado_em = datetime.utcnow()
    session.add(pedido)


def atualizar_status_por_lancamento(session: Session, pedido_id: int, valor_lancamento: float) -> None:
    """Chamado por `financeiro.py` quando um lançamento é vinculado a um
    pedido — soma o valor lançado distribuído pelos itens em aberto (por
    ordem de cadastro) e recalcula o status do pedido."""
    pedido = session.get(Pedido, pedido_id)
    if not pedido:
        return
    itens = session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id).order_by(PedidoItem.id)).all()
    restante = valor_lancamento
    for it in itens:
        if restante <= 0:
            break
        falta = max(0.0, it.valor_total_estimado - it.valor_atendido)
        if falta <= 0:
            continue
        aplicar = min(falta, restante)
        it.valor_atendido = round(it.valor_atendido + aplicar, 2)
        restante = round(restante - aplicar, 2)
        session.add(it)
    _recalcular_status(session, pedido)
    session.commit()


def atualizar_status_por_movimento_estoque(session: Session, pedido_item_id: int, quantidade: float) -> None:
    """Chamado por `estoque.py` quando uma entrada de estoque é vinculada a
    um item de pedido — soma a quantidade recebida e recalcula o status."""
    item = session.get(PedidoItem, pedido_item_id)
    if not item:
        return
    item.quantidade_atendida = round((item.quantidade_atendida or 0) + quantidade, 2)
    session.add(item)
    pedido = session.get(Pedido, item.pedido_id)
    if pedido:
        _recalcular_status(session, pedido)
    session.commit()


@router.get("/opcoes")
def opcoes(session: Session = Depends(get_session)) -> dict:
    """Listas para os seletores do formulário de Pedido — mesmo padrão de
    `GET /financeiro/opcoes`, reaproveitando os cadastros já existentes."""
    fornecedores = session.exec(select(Fornecedor).where(Fornecedor.ativo == True)).all()
    servicos = session.exec(select(ServicoCadastro).where(ServicoCadastro.ativo == True)).all()
    return {
        "fornecedores": sorted({f.nome for f in fornecedores if f.tipo in ("fornecedor", "fabricante")}),
        "clientes": sorted({f.nome for f in fornecedores if f.tipo == "cliente"}),
        "servicos": sorted({s.nome for s in servicos}),
    }


@router.get("/")
def listar_pedidos(
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    fornecedor_cliente: Optional[str] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    session: Session = Depends(get_session),
) -> list[dict]:
    pedidos = session.exec(select(Pedido).order_by(Pedido.data_pedido.desc())).all()
    itens_por_pedido: dict[int, list[dict]] = {}
    for it in session.exec(select(PedidoItem)).all():
        itens_por_pedido.setdefault(it.pedido_id, []).append(it.model_dump())

    resultado = []
    for p in pedidos:
        if tipo and p.tipo != tipo:
            continue
        if status and p.status != status:
            continue
        if fornecedor_cliente and p.fornecedor_cliente != fornecedor_cliente:
            continue
        if data_inicio and p.data_pedido < data_inicio:
            continue
        if data_fim and p.data_pedido > data_fim:
            continue
        itens = itens_por_pedido.get(p.id, [])
        d = p.model_dump()
        d["itens"] = itens
        d["valor_total_estimado"] = round(sum(i["valor_total_estimado"] for i in itens), 2)
        d["valor_atendido"] = round(sum(i["valor_atendido"] for i in itens), 2)
        resultado.append(d)
    return resultado


@router.get("/{pedido_id}")
def obter_pedido(pedido_id: int, session: Session = Depends(get_session)) -> dict:
    pedido = session.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    itens = session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id)).all()
    lancamentos = session.exec(select(ContaGerencial).where(ContaGerencial.pedido_id == pedido_id)).all()
    movimentos = session.exec(select(MovimentoEstoque).where(MovimentoEstoque.pedido_id == pedido_id)).all()
    d = pedido.model_dump()
    d["itens"] = [i.model_dump() for i in itens]
    d["lancamentos"] = [l.model_dump() for l in lancamentos]
    d["movimentos_estoque"] = [m.model_dump() for m in movimentos]
    return d


@router.post("/", status_code=201)
def criar_pedido(dados: PedidoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    if dados.tipo not in ("compra", "venda"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'compra' ou 'venda'")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um produto ou serviço")

    numero_pedido = _proximo_numero_pedido(session, dados.data_pedido.year)
    pedido = Pedido(
        numero_pedido=numero_pedido,
        tipo=dados.tipo,
        fornecedor_cliente=dados.fornecedor_cliente,
        centro_custo=mapear_centro_custo(dados.centro_custo) if dados.centro_custo else None,
        data_pedido=dados.data_pedido,
        data_prevista=dados.data_prevista,
        observacao=dados.observacao,
        responsavel=dados.responsavel,
        origem_tipo=dados.origem_tipo,
        origem_item_id=dados.origem_item_id,
        usuario_id=user.id if isinstance(user, Usuario) else None,
    )
    session.add(pedido)
    session.commit()
    session.refresh(pedido)

    for item in dados.itens:
        session.add(PedidoItem(
            pedido_id=pedido.id,
            tipo_item=item.tipo_item,
            produto_servico=item.produto_servico,
            codigo_conta_gerencial=item.codigo_conta_gerencial,
            nome_conta_gerencial=item.nome_conta_gerencial,
            quantidade=item.quantidade,
            valor_unitario_estimado=item.valor_unitario_estimado,
            valor_total_estimado=item.valor_total_estimado,
        ))
    session.commit()
    return {"id": pedido.id, "numero_pedido": numero_pedido}


@router.put("/{pedido_id}")
def atualizar_pedido(pedido_id: int, dados: PedidoIn, session: Session = Depends(get_session)) -> dict:
    pedido = session.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if pedido.tipo not in ("compra", "venda") and dados.tipo not in ("compra", "venda"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'compra' ou 'venda'")

    pedido.tipo = dados.tipo
    pedido.fornecedor_cliente = dados.fornecedor_cliente
    pedido.centro_custo = mapear_centro_custo(dados.centro_custo) if dados.centro_custo else None
    pedido.data_pedido = dados.data_pedido
    pedido.data_prevista = dados.data_prevista
    pedido.observacao = dados.observacao
    pedido.responsavel = dados.responsavel
    pedido.atualizado_em = datetime.utcnow()
    session.add(pedido)

    # Substitui os itens — mais simples e seguro do que tentar casar item a
    # item; o "atendido" já registrado fica preservado nos itens que baterem
    # por produto/serviço (heurística simples, suficiente para edição manual).
    antigos = session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id)).all()
    atendido_por_produto = {i.produto_servico: (i.quantidade_atendida, i.valor_atendido) for i in antigos}
    for i in antigos:
        session.delete(i)
    for item in dados.itens:
        qtd_atendida, val_atendido = atendido_por_produto.get(item.produto_servico, (0, 0))
        session.add(PedidoItem(
            pedido_id=pedido_id,
            tipo_item=item.tipo_item,
            produto_servico=item.produto_servico,
            codigo_conta_gerencial=item.codigo_conta_gerencial,
            nome_conta_gerencial=item.nome_conta_gerencial,
            quantidade=item.quantidade,
            valor_unitario_estimado=item.valor_unitario_estimado,
            valor_total_estimado=item.valor_total_estimado,
            quantidade_atendida=qtd_atendida,
            valor_atendido=val_atendido,
        ))
    session.commit()
    _recalcular_status(session, pedido)
    session.commit()
    return {"id": pedido.id}


class StatusIn(BaseModel):
    status: str  # "aberto" | "parcialmente_atendido" | "atendido" | "cancelado"


@router.put("/{pedido_id}/status")
def atualizar_status_pedido(pedido_id: int, dados: StatusIn, session: Session = Depends(get_session)) -> dict:
    pedido = session.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if dados.status not in ("aberto", "parcialmente_atendido", "atendido", "cancelado"):
        raise HTTPException(status_code=400, detail="Status inválido")
    pedido.status = dados.status
    pedido.atualizado_em = datetime.utcnow()
    session.add(pedido)
    session.commit()
    return {"id": pedido.id, "status": pedido.status}


@router.delete("/{pedido_id}", status_code=204)
def excluir_pedido(pedido_id: int, session: Session = Depends(get_session)) -> None:
    pedido = session.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    vinculado = session.exec(select(ContaGerencial).where(ContaGerencial.pedido_id == pedido_id)).first()
    if vinculado:
        raise HTTPException(status_code=400, detail="Este pedido já tem lançamento financeiro vinculado — não pode ser excluído")
    for i in session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id)).all():
        session.delete(i)
    session.delete(pedido)
    session.commit()
