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

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import (
    CATEGORIAS_PEDIDO_ANEXO, ContaGerencial, Fornecedor, MovimentoEstoque, Pedido, PedidoAnexo, PedidoItem, ServicoCadastro, Usuario,
)
from fazenda.rules import estoque_baixa
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.centro_custo import mapear_centro_custo
from fazenda.rules.pedido_status import STATUS_CANCELADO, calcular_status_pedido
from fazenda.rules.supabase_storage import baixar_arquivo, enviar_arquivo, excluir_arquivo, nome_seguro_storage

router = APIRouter(prefix="/pedidos", tags=["pedidos"])


def _proximo_numero_pedido(session: Session, ano: int, fazenda_id: int | None = None) -> str:
    prefixo = f"PED-{ano}-"
    query = select(Pedido.numero_pedido).where(Pedido.numero_pedido.like(f"{prefixo}%"))
    if fazenda_id is not None:
        query = query.where(Pedido.fazenda_id == fazenda_id)
    existentes = session.exec(query).all()
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


def atualizar_status_por_lancamento(
    session: Session, pedido_id: int, valor_lancamento: float, fazenda_id: int | None = None,
) -> None:
    """Chamado por `financeiro.py` quando um lançamento é vinculado a um
    pedido — soma o valor lançado distribuído pelos itens em aberto (por
    ordem de cadastro). `fazenda_id` (já a da fazenda do lançamento que está
    sendo criado) precisa bater com a do pedido — senão um pedido de outra
    fazenda poderia ser atualizado só por quem soubesse o id dele.

    NÃO mexe mais em `Pedido.status` — dinheiro lançado é informativo
    (`valor_atendido`, usado por ex. em `GET /pedidos`), quem decide o
    status é só entrega física (`quantidade_entregue`, ver
    `marcar_entrega_item_pedido` e o docstring de
    `fazenda.rules.pedido_status`)."""
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
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
    session.commit()


def atualizar_status_por_movimento_estoque(session: Session, pedido_item_id: int, quantidade: float) -> None:
    """Chamado por `estoque.py` quando uma entrada de estoque é vinculada a
    um item de pedido — soma a quantidade recebida em `quantidade_atendida`
    (informativo). NÃO mexe em `Pedido.status` — mesmo motivo de
    `atualizar_status_por_lancamento` acima."""
    item = session.get(PedidoItem, pedido_item_id)
    if not item:
        return
    item.quantidade_atendida = round((item.quantidade_atendida or 0) + quantidade, 2)
    session.add(item)
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
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_pedidos = select(Pedido)
    query_itens = select(PedidoItem)
    if fazenda_id is not None:
        query_pedidos = query_pedidos.where(Pedido.fazenda_id == fazenda_id)
        query_itens = query_itens.where(PedidoItem.fazenda_id == fazenda_id)
    pedidos = session.exec(query_pedidos.order_by(Pedido.data_pedido.desc())).all()
    itens_por_pedido: dict[int, list[dict]] = {}
    for it in session.exec(query_itens).all():
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
def obter_pedido(
    pedido_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
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
def criar_pedido(
    dados: PedidoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if dados.tipo not in ("compra", "venda"):
        raise HTTPException(status_code=400, detail="tipo deve ser 'compra' ou 'venda'")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um produto ou serviço")

    numero_pedido = _proximo_numero_pedido(session, dados.data_pedido.year, fazenda_id)
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
        fazenda_id=fazenda_id,
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
            fazenda_id=fazenda_id,
        ))
    session.commit()
    return {"id": pedido.id, "numero_pedido": numero_pedido}


@router.put("/{pedido_id}")
def atualizar_pedido(
    pedido_id: int, dados: PedidoIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
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
    # item; o "atendido" (financeiro/estoque) E o "entregue" (físico) já
    # registrados ficam preservados nos itens que baterem por produto/
    # serviço (heurística simples, suficiente para edição manual). Sem isso,
    # editar um pedido (ex.: corrigir um valor) apagaria a entrega já
    # marcada e o status voltaria a "aberto" por baixo do usuário.
    antigos = session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id)).all()
    atendido_por_produto = {
        i.produto_servico: (i.quantidade_atendida, i.valor_atendido, i.quantidade_entregue) for i in antigos
    }
    for i in antigos:
        session.delete(i)
    for item in dados.itens:
        qtd_atendida, val_atendido, qtd_entregue = atendido_por_produto.get(item.produto_servico, (0, 0, 0))
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
            quantidade_entregue=qtd_entregue,
            fazenda_id=fazenda_id,
        ))
    session.commit()

    # Status é CALCULADO a partir da entrega dos itens recriados acima —
    # mesma função usada por `marcar_entrega_item_pedido`, único outro
    # escritor de `Pedido.status` (ver fazenda.rules.pedido_status).
    itens_atuais = session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id)).all()
    pedido.status = calcular_status_pedido(itens_atuais, pedido.status)
    pedido.atualizado_em = datetime.utcnow()
    session.add(pedido)
    session.commit()
    return {"id": pedido.id}


class StatusIn(BaseModel):
    # Único valor aceito hoje é "cancelado" — os demais status ("aberto",
    # "parcialmente_atendido", "atendido") são CALCULADOS a partir da
    # entrega física dos itens (ver `calcular_status_pedido` e
    # `PUT /{pedido_id}/itens/{item_id}/entrega`) e não podem mais ser
    # escritos manualmente. Cancelamento continua sendo a única transição
    # manual porque não há "quanto foi entregue" que o descreva — é uma
    # decisão do usuário, não um fato de estoque.
    status: str


@router.put("/{pedido_id}/status")
def atualizar_status_pedido(
    pedido_id: int,
    dados: StatusIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Hoje só cancela o pedido (ver `StatusIn`) — único caller no frontend é
    o botão "Cancelar pedido" da tela de Pedidos. Cancelamento é terminal
    (mesma regra de `calcular_status_pedido`): mesmo um pedido já
    "atendido" pode ser cancelado aqui, e depois disso a entrega física
    marcada não volta a mexer no status."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if dados.status != STATUS_CANCELADO:
        raise HTTPException(
            status_code=400,
            detail=(
                "Status é calculado a partir da entrega física dos itens "
                "(ver PUT /{pedido_id}/itens/{item_id}/entrega) — este endpoint só aceita 'cancelado'"
            ),
        )
    pedido.status = STATUS_CANCELADO
    pedido.atualizado_em = datetime.utcnow()
    session.add(pedido)
    session.commit()
    return {"id": pedido.id, "status": pedido.status}


class RastreioIn(BaseModel):
    enviado: bool
    codigo_rastreio: Optional[str] = None
    link_rastreio: Optional[str] = None


@router.put("/{pedido_id}/rastreio")
def atualizar_rastreio_pedido(
    pedido_id: int,
    dados: RastreioIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Perguntado quando o status manual vira "parcialmente_atendido" (ver
    tela de Pedidos): se o pedido já foi enviado, guarda o código de
    rastreio e o link de acompanhamento. `enviado=False` limpa os dois
    campos (usuário respondeu que ainda não foi enviado)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    pedido.enviado = dados.enviado
    pedido.codigo_rastreio = dados.codigo_rastreio if dados.enviado else None
    pedido.link_rastreio = dados.link_rastreio if dados.enviado else None
    pedido.atualizado_em = datetime.utcnow()
    session.add(pedido)
    session.commit()
    return {"id": pedido.id, "enviado": pedido.enviado, "codigo_rastreio": pedido.codigo_rastreio, "link_rastreio": pedido.link_rastreio}


class PedidoItemEntregaIn(BaseModel):
    quantidade_entregue: float  # valor ABSOLUTO novo do item (replace, não delta) — mesmo padrão de PUT /cadastro/diarias/{id}/dias


def _pendencias_fechamento_pedido(session: Session, pedido_id: int) -> list[str]:
    """O que falta para este pedido estar "fechado de verdade" no Financeiro,
    reaproveitando a mesma consulta de `GET /pedidos/{id}` (ContaGerencial
    vinculado por `pedido_id`).

    Sem NENHUM lançamento vinculado ainda, faltam os dois dados que fecham a
    ponta financeira de uma nota (ver `criar_lancamento`/`FormFinanceiro.tsx`):
    quando/quanto foi pago (`data_pagamento`) e a data de emissão do documento
    (`data_emissao`). Com pelo menos um lançamento já vinculado, cada campo só
    conta como pendente se NENHUMA parcela o tiver preenchido — parcelado em
    3x com a 1ª já paga não deve pedir "pagamento" de novo."""
    lancamentos = session.exec(select(ContaGerencial).where(ContaGerencial.pedido_id == pedido_id)).all()
    if not lancamentos:
        return ["pagamento", "data_emissao"]
    pendencias = []
    if not any(l.data_pagamento for l in lancamentos):
        pendencias.append("pagamento")
    if not any(l.data_emissao for l in lancamentos):
        pendencias.append("data_emissao")
    return pendencias


@router.put("/{pedido_id}/itens/{item_id}/entrega")
def marcar_entrega_item_pedido(
    pedido_id: int,
    item_id: int,
    dados: PedidoItemEntregaIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Marca quanto de um item do Pedido já foi FISICAMENTE entregue —
    escreve `PedidoItem.quantidade_entregue` (substitui, não soma; ver
    `PedidoItemEntregaIn`) e é o ÚNICO escritor deste campo: dinheiro lançado
    (`atualizar_status_por_lancamento`) ou estoque baixado por outro caminho
    (`atualizar_status_por_movimento_estoque`) nunca mexem aqui, e vice-versa
    — ver comentário em `PedidoItem.quantidade_entregue`.

    Depois de gravar, `Pedido.status` deixa de ser lido/escrito diretamente e
    passa a ser CALCULADO por `calcular_status_pedido` a partir da entrega de
    todos os itens do pedido — não só deste.

    Decisão de produto: pedido `cancelado` é terminal (mesma regra de
    `calcular_status_pedido`) e não aceita marcação de entrega nenhuma — nem
    para o status "voltar" a refletir entrega. Permitir mexeria em estoque e
    devolveria pendências financeiras de um pedido que o usuário já decidiu
    encerrar; se a entrega foi um engano de fato, o caminho é reabrir o
    pedido explicitamente (fora do escopo desta ação), não marcar entrega por
    cima de um cancelamento.
    """
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    item = session.get(PedidoItem, item_id)
    if not item or item.pedido_id != pedido_id or (fazenda_id is not None and item.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Item do pedido não encontrado")
    if pedido.status == STATUS_CANCELADO:
        raise HTTPException(status_code=400, detail="Pedido cancelado não aceita marcação de entrega")
    if dados.quantidade_entregue < 0:
        raise HTTPException(status_code=400, detail="quantidade_entregue não pode ser negativa")

    anterior = item.quantidade_entregue or 0.0
    delta = dados.quantidade_entregue - anterior
    item.quantidade_entregue = dados.quantidade_entregue
    session.add(item)
    session.flush()

    # Item estocável (tipo_item == "produto") com AUMENTO na entrega: dá
    # entrada automática no estoque, na mesma transação (Decisão A1 da
    # proposta) — mesmo padrão atômico de compra_semen.py (nota + estoque +
    # registro de domínio juntos, um único commit). Uma correção para baixo
    # (usuário exagerou e está ajustando) ou item de serviço nunca mexem em
    # estoque: não há "desfazer entrada" automático aqui, de propósito — é
    # ajuste raro o bastante para não valer o risco de estornar estoque
    # errado sozinho.
    avisos_estoque: list[str] = []
    if item.tipo_item == "produto" and delta > 0:
        estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=item.produto_servico)
        avisos_estoque = estoque_baixa.movimentar(
            session, item=estoque_item, quantidade=delta,
            unidade=estoque_item.unidade if estoque_item else None,
            data=date.today(), fazenda_id=fazenda_id, movimento="Entrada de compra",
            observacao=f"Entrega de {pedido.numero_pedido} — {item.produto_servico}",
            usuario_id=user.id if isinstance(user, Usuario) else None, sinal=+1,
            produto=item.produto_servico, pedido_id=pedido_id, pedido_item_id=item.id,
        )

    itens_pedido = session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id)).all()
    pedido.status = calcular_status_pedido(itens_pedido, pedido.status)
    pedido.atualizado_em = datetime.utcnow()
    session.add(pedido)
    session.commit()
    session.refresh(pedido)
    session.refresh(item)

    return {
        "id": pedido.id,
        "status": pedido.status,
        "pendencias": _pendencias_fechamento_pedido(session, pedido_id),
        "avisos_estoque": avisos_estoque,
        "item": {"id": item.id, "quantidade_entregue": item.quantidade_entregue},
    }


# Tamanho máximo por anexo — mesmo limite de LancamentoAnexo (ver financeiro.py).
TAMANHO_MAXIMO_ANEXO_PEDIDO = 15 * 1024 * 1024  # 15 MB


def _caminho_anexo_pedido(session: Session, fazenda_id: int | None, pedido_id: int, nome_arquivo: str) -> str:
    """fazenda-X/pedidos/{pedido_id}/0001_nome.ext — sequencial dentro do pedido."""
    pasta = f"fazenda-{fazenda_id if fazenda_id is not None else 'geral'}/pedidos/{pedido_id}"
    existentes = session.exec(select(PedidoAnexo).where(PedidoAnexo.pedido_id == pedido_id)).all()
    seq = 1 + len(existentes)
    return f"{pasta}/{seq:04d}_{nome_seguro_storage(nome_arquivo)}"


@router.post("/{pedido_id}/anexos", status_code=201)
async def anexar_arquivo_pedido(
    pedido_id: int, file: UploadFile, categoria: str = Form(...),
    data_validade: Optional[date] = Form(None),
    session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Anexa um orçamento, ordem de serviço ou outro documento a um pedido já
    criado. Se `data_validade` for informada, a Agenda passa a alertar 2 dias
    antes do vencimento enquanto o pedido seguir aberto ou parcialmente
    atendido (ver fazenda/rules/agenda_engine.py)."""
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if categoria not in CATEGORIAS_PEDIDO_ANEXO:
        raise HTTPException(status_code=400, detail=f"categoria deve ser uma de: {', '.join(CATEGORIAS_PEDIDO_ANEXO)}")
    conteudo = await file.read()
    if len(conteudo) > TAMANHO_MAXIMO_ANEXO_PEDIDO:
        raise HTTPException(status_code=400, detail="Arquivo maior que 15 MB — não é possível anexar")
    nome_arquivo = file.filename or "arquivo"
    caminho = _caminho_anexo_pedido(session, fazenda_id, pedido_id, nome_arquivo)
    try:
        enviar_arquivo(caminho, conteudo, file.content_type or "application/octet-stream", bucket=settings.supabase_bucket_financeiro)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    anexo = PedidoAnexo(
        pedido_id=pedido_id,
        nome_arquivo=nome_arquivo,
        mime_type=file.content_type or "application/octet-stream",
        tamanho_bytes=len(conteudo),
        categoria=categoria,
        data_validade=data_validade,
        caminho_storage=caminho,
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id,
    )
    session.add(anexo)
    session.commit()
    session.refresh(anexo)
    return {
        "id": anexo.id, "nome_arquivo": anexo.nome_arquivo, "mime_type": anexo.mime_type,
        "tamanho_bytes": anexo.tamanho_bytes, "categoria": anexo.categoria,
        "data_validade": anexo.data_validade.isoformat() if anexo.data_validade else None,
    }


@router.get("/{pedido_id}/anexos")
def listar_anexos_pedido(
    pedido_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    anexos = session.exec(select(PedidoAnexo).where(PedidoAnexo.pedido_id == pedido_id)).all()
    return [
        {"id": a.id, "nome_arquivo": a.nome_arquivo, "mime_type": a.mime_type, "tamanho_bytes": a.tamanho_bytes,
         "categoria": a.categoria, "data_validade": a.data_validade.isoformat() if a.data_validade else None,
         "criado_em": a.criado_em.isoformat()}
        for a in anexos
    ]


@router.get("/anexos/{anexo_id}")
def baixar_anexo_pedido(
    anexo_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> Response:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = session.get(PedidoAnexo, anexo_id)
    if not anexo or (fazenda_id is not None and anexo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    try:
        conteudo = baixar_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=conteudo, media_type=anexo.mime_type,
        headers={"Content-Disposition": f'inline; filename="{anexo.nome_arquivo}"'},
    )


@router.delete("/anexos/{anexo_id}")
def excluir_anexo_pedido(
    anexo_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    anexo = session.get(PedidoAnexo, anexo_id)
    if not anexo or (fazenda_id is not None and anexo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    if anexo.caminho_storage:
        try:
            excluir_arquivo(anexo.caminho_storage, bucket=settings.supabase_bucket_financeiro)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    session.delete(anexo)
    session.commit()
    return {"excluido": True}


@router.delete("/{pedido_id}", status_code=204)
def excluir_pedido(
    pedido_id: int,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> None:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pedido = session.get(Pedido, pedido_id)
    if not pedido or (fazenda_id is not None and pedido.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    vinculado = session.exec(select(ContaGerencial).where(ContaGerencial.pedido_id == pedido_id)).first()
    if vinculado:
        raise HTTPException(status_code=400, detail="Este pedido já tem lançamento financeiro vinculado — não pode ser excluído")
    for a in session.exec(select(PedidoAnexo).where(PedidoAnexo.pedido_id == pedido_id)).all():
        if a.caminho_storage:
            try:
                excluir_arquivo(a.caminho_storage, bucket=settings.supabase_bucket_financeiro)
            except RuntimeError:
                pass
        session.delete(a)
    for i in session.exec(select(PedidoItem).where(PedidoItem.pedido_id == pedido_id)).all():
        session.delete(i)
    session.delete(pedido)
    session.commit()
