"""
Router de Cotação de Preços com Fornecedores — pede preço a vários
fornecedores por categoria, compara as respostas, e gera Pedidos reais
(`fazenda.rules.cotacao.gerar_pedidos_da_cotacao`) com os vencedores
escolhidos. Reaproveita o módulo comercial "pedidos" já cadastrado em
main.py (mesma trava de `exigir_modulo`/`exigir_modulo_contratado` +
`exigir_fazenda_selecionada` que já protege `/pedidos`) em vez de criar um
módulo contratável novo só pra isto.

Os endpoints PÚBLICOS (sem login) que o fornecedor usa para responder à
cotação ou confirmar um pedido formal vivem em `publico.py`, num router
separado registrado SEM as travas acima — nunca aqui.
"""
from __future__ import annotations

import logging
import secrets
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import (
    Cotacao, CotacaoFornecedor, CotacaoItem, CotacaoResposta, Estoque, Fazenda, Fornecedor, FornecedorCategoria,
    Usuario,
)
from fazenda.rules import cotacao as cotacao_rules
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.email import enviar_email
from fazenda.rules.whatsapp_evolution import enviar_whatsapp

router = APIRouter(prefix="/cotacoes", tags=["cotacoes"])
logger = logging.getLogger(__name__)


def _proximo_numero_cotacao(session: Session, ano: int, fazenda_id: int | None) -> str:
    prefixo = f"COT-{ano}-"
    query = select(Cotacao.numero_cotacao).where(Cotacao.numero_cotacao.like(f"{prefixo}%"))
    if fazenda_id is not None:
        query = query.where(Cotacao.fazenda_id == fazenda_id)
    existentes = session.exec(query).all()
    maior = 0
    for n in existentes:
        if n and n.startswith(prefixo):
            try:
                maior = max(maior, int(n[len(prefixo):]))
            except ValueError:
                continue
    return f"{prefixo}{maior + 1:05d}"


def _cotacao_da_fazenda(session: Session, cotacao_id: int, fazenda_id: int | None) -> Cotacao:
    c = session.get(Cotacao, cotacao_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not c or (fazenda_id is not None and c.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Cotação não encontrada")
    return c


# ---------------------------------------------------------------------------
# Sugestão de fornecedores por categoria
# ---------------------------------------------------------------------------
@router.get("/opcoes/fornecedores-sugeridos")
def fornecedores_sugeridos(
    categoria: str, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    """Fornecedores DESTA fazenda vinculados à categoria (FornecedorCategoria)
    — usado pra pré-marcar a lista na tela de Nova cotação."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = (
        select(Fornecedor)
        .join(FornecedorCategoria, FornecedorCategoria.fornecedor_id == Fornecedor.id)
        .where(FornecedorCategoria.categoria == categoria, Fornecedor.ativo == True)  # noqa: E712
    )
    if fazenda_id is not None:
        query = query.where(Fornecedor.fazenda_id == fazenda_id)
    fornecedores = session.exec(query.order_by(Fornecedor.nome)).all()
    return [f.model_dump() for f in fornecedores]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
class CotacaoItemIn(BaseModel):
    estoque_id: Optional[int] = None
    produto: str
    quantidade: float
    unidade: Optional[str] = None


class CotacaoFornecedorIn(BaseModel):
    fornecedor_id: int
    canal: str = "email"  # "email" | "whatsapp" | "ambos"


class CotacaoIn(BaseModel):
    categoria: str
    modo: str = "completo"
    prazo_resposta: datetime
    observacao: Optional[str] = None
    itens: list[CotacaoItemIn]
    fornecedores: list[CotacaoFornecedorIn]


@router.get("/")
def listar_cotacoes(
    status: Optional[str] = None, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Cotacao)
    if fazenda_id is not None:
        query = query.where(Cotacao.fazenda_id == fazenda_id)
    if status:
        query = query.where(Cotacao.status == status)
    cotacoes = session.exec(query.order_by(Cotacao.criado_em.desc())).all()
    resultado = []
    for c in cotacoes:
        convites = session.exec(select(CotacaoFornecedor).where(CotacaoFornecedor.cotacao_id == c.id)).all()
        d = c.model_dump()
        d["total_fornecedores"] = len(convites)
        d["total_respondidos"] = sum(1 for f in convites if f.status_envio in ("respondido", "recusado"))
        resultado.append(d)
    return resultado


@router.get("/{cotacao_id}")
def obter_cotacao(
    cotacao_id: int, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    c = _cotacao_da_fazenda(session, cotacao_id, fazenda_id)
    itens = session.exec(select(CotacaoItem).where(CotacaoItem.cotacao_id == c.id)).all()
    convites = session.exec(select(CotacaoFornecedor).where(CotacaoFornecedor.cotacao_id == c.id)).all()
    ids_fornecedor = [cf.fornecedor_id for cf in convites]
    nomes = {}
    if ids_fornecedor:
        nomes = {f.id: f.nome for f in session.exec(select(Fornecedor).where(Fornecedor.id.in_(ids_fornecedor))).all()}
    respostas = session.exec(
        select(CotacaoResposta)
        .join(CotacaoFornecedor, CotacaoResposta.cotacao_fornecedor_id == CotacaoFornecedor.id)
        .where(CotacaoFornecedor.cotacao_id == c.id)
    ).all()
    d = c.model_dump()
    d["itens"] = [i.model_dump() for i in itens]
    d["fornecedores"] = [{**cf.model_dump(), "fornecedor_nome": nomes.get(cf.fornecedor_id)} for cf in convites]
    d["respostas"] = [r.model_dump() for r in respostas]
    return d


@router.post("/", status_code=201)
def criar_cotacao(
    dados: CotacaoIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um item")
    if not dados.fornecedores:
        raise HTTPException(status_code=400, detail="Selecione ao menos um fornecedor")

    numero = _proximo_numero_cotacao(session, date.today().year, fazenda_id)
    c = Cotacao(
        numero_cotacao=numero, categoria=dados.categoria, modo=dados.modo,
        prazo_resposta=dados.prazo_resposta, observacao=dados.observacao,
        usuario_id=user.id if isinstance(user, Usuario) else None,
        fazenda_id=fazenda_id, status=cotacao_rules.STATUS_RASCUNHO,
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    for item in dados.itens:
        # `estoque_id`, se veio, precisa ser desta fazenda — nunca confia
        # cegamente no id que o cliente mandou (poderia ser de outra fazenda,
        # advinhado por id sequencial).
        estoque_id = item.estoque_id
        if estoque_id is not None:
            est = session.get(Estoque, estoque_id)
            if not est or est.fazenda_id != fazenda_id:
                estoque_id = None
        session.add(CotacaoItem(
            cotacao_id=c.id, estoque_id=estoque_id, produto=item.produto,
            quantidade=item.quantidade, unidade=item.unidade, fazenda_id=fazenda_id,
        ))

    for forn in dados.fornecedores:
        fornecedor = session.get(Fornecedor, forn.fornecedor_id)
        if not fornecedor or fornecedor.fazenda_id != fazenda_id:
            raise HTTPException(status_code=400, detail="Fornecedor inválido")
        if forn.canal not in ("email", "whatsapp", "ambos"):
            raise HTTPException(status_code=400, detail="Canal inválido")
        session.add(CotacaoFornecedor(
            cotacao_id=c.id, fornecedor_id=fornecedor.id, canal=forn.canal,
            token_publico=secrets.token_urlsafe(32), fazenda_id=fazenda_id,
        ))
    session.commit()
    return {"id": c.id, "numero_cotacao": numero}


@router.delete("/{cotacao_id}", status_code=204)
def excluir_cotacao(
    cotacao_id: int, fazenda_id: int = Depends(get_fazenda_id_escrita), session: Session = Depends(get_session),
) -> None:
    c = _cotacao_da_fazenda(session, cotacao_id, fazenda_id)
    if c.status != cotacao_rules.STATUS_RASCUNHO:
        raise HTTPException(status_code=400, detail="Só é possível excluir uma cotação ainda em rascunho — cancele as demais.")
    for cf in session.exec(select(CotacaoFornecedor).where(CotacaoFornecedor.cotacao_id == c.id)).all():
        session.delete(cf)
    for item in session.exec(select(CotacaoItem).where(CotacaoItem.cotacao_id == c.id)).all():
        session.delete(item)
    session.delete(c)
    session.commit()


# ---------------------------------------------------------------------------
# Disparo
# ---------------------------------------------------------------------------
class DisparoIn(BaseModel):
    mensagem: Optional[str] = None  # None = usa o texto padrão sugerido


@router.post("/{cotacao_id}/disparar")
def disparar_cotacao(
    cotacao_id: int, dados: DisparoIn = DisparoIn(), session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    c = _cotacao_da_fazenda(session, cotacao_id, fazenda_id)
    if c.status not in (cotacao_rules.STATUS_RASCUNHO, cotacao_rules.STATUS_ENVIADA):
        raise HTTPException(status_code=400, detail="Esta cotação não está mais em rascunho/enviada")

    fazenda = session.get(Fazenda, fazenda_id)
    nome_fazenda = fazenda.nome if fazenda else "a fazenda"
    convites = session.exec(select(CotacaoFornecedor).where(CotacaoFornecedor.cotacao_id == c.id)).all()
    erros: list[str] = []
    for cf in convites:
        if cf.status_envio not in ("pendente", "falha_envio"):
            continue
        fornecedor = session.get(Fornecedor, cf.fornecedor_id)
        if not fornecedor:
            continue
        link = f"{settings.frontend_base_url}/cotacao/{cf.token_publico}"
        texto = dados.mensagem or cotacao_rules.montar_mensagem_cotacao(nome_fazenda, link)
        ok = True
        try:
            if cf.canal in ("email", "ambos"):
                if not fornecedor.email:
                    raise RuntimeError(f'Fornecedor "{fornecedor.nome}" não tem e-mail cadastrado.')
                enviar_email(fornecedor.email, f"Cotação {c.numero_cotacao} — {nome_fazenda}", f"<p>{texto}</p>")
            if cf.canal in ("whatsapp", "ambos"):
                if not fornecedor.telefone:
                    raise RuntimeError(f'Fornecedor "{fornecedor.nome}" não tem telefone cadastrado.')
                enviar_whatsapp(fornecedor.telefone, texto)
        except RuntimeError as e:
            ok = False
            erros.append(f"{fornecedor.nome}: {e}")
        cf.status_envio = "enviado" if ok else "falha_envio"
        cf.enviado_em = datetime.utcnow()
        session.add(cf)
    c.status = cotacao_rules.STATUS_ENVIADA
    c.atualizado_em = datetime.utcnow()
    session.add(c)
    session.commit()
    return {"status": c.status, "erros": erros}


# ---------------------------------------------------------------------------
# Comparação e geração de pedidos
# ---------------------------------------------------------------------------
class MarcarVencedorIn(BaseModel):
    cotacao_item_id: int
    cotacao_fornecedor_id: int


@router.put("/{cotacao_id}/vencedores")
def marcar_vencedores(
    cotacao_id: int, dados: list[MarcarVencedorIn], session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    c = _cotacao_da_fazenda(session, cotacao_id, fazenda_id)
    if c.status == cotacao_rules.STATUS_PEDIDOS_GERADOS:
        raise HTTPException(status_code=400, detail="Esta cotação já gerou pedidos — não é mais possível mudar vencedores.")
    for escolha in dados:
        item = session.get(CotacaoItem, escolha.cotacao_item_id)
        if not item or item.cotacao_id != c.id:
            raise HTTPException(status_code=400, detail="Item inválido para esta cotação")
        cf = session.get(CotacaoFornecedor, escolha.cotacao_fornecedor_id)
        if not cf or cf.cotacao_id != c.id:
            raise HTTPException(status_code=400, detail="Fornecedor inválido para esta cotação")
        respostas_do_item = session.exec(
            select(CotacaoResposta)
            .join(CotacaoFornecedor, CotacaoResposta.cotacao_fornecedor_id == CotacaoFornecedor.id)
            .where(CotacaoFornecedor.cotacao_id == c.id, CotacaoResposta.cotacao_item_id == item.id)
        ).all()
        for r in respostas_do_item:
            r.vencedor = (r.cotacao_fornecedor_id == cf.id)
            session.add(r)
    c.status = cotacao_rules.STATUS_COMPARADA
    c.atualizado_em = datetime.utcnow()
    session.add(c)
    session.commit()
    return {"status": c.status}


@router.post("/{cotacao_id}/gerar-pedidos", status_code=201)
def gerar_pedidos(
    cotacao_id: int, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    c = _cotacao_da_fazenda(session, cotacao_id, fazenda_id)
    if c.status != cotacao_rules.STATUS_COMPARADA:
        raise HTTPException(status_code=400, detail="Marque os vencedores (Comparação) antes de gerar pedidos.")
    pedidos = cotacao_rules.gerar_pedidos_da_cotacao(
        session, cotacao=c, fazenda_id=fazenda_id, usuario_id=user.id if isinstance(user, Usuario) else None,
    )
    if not pedidos:
        raise HTTPException(status_code=400, detail="Nenhum vencedor marcado — não há o que gerar.")
    c.status = cotacao_rules.STATUS_PEDIDOS_GERADOS
    c.atualizado_em = datetime.utcnow()
    session.add(c)
    session.commit()
    return {"pedidos": [{"id": p.id, "numero_pedido": p.numero_pedido} for p in pedidos]}


@router.post("/{cotacao_id}/cancelar")
def cancelar_cotacao(
    cotacao_id: int, fazenda_id: int = Depends(get_fazenda_id_escrita), session: Session = Depends(get_session),
) -> dict:
    c = _cotacao_da_fazenda(session, cotacao_id, fazenda_id)
    if c.status == cotacao_rules.STATUS_PEDIDOS_GERADOS:
        raise HTTPException(status_code=400, detail="Esta cotação já gerou pedidos — cancele os pedidos individualmente, se for o caso.")
    c.status = cotacao_rules.STATUS_CANCELADA
    c.atualizado_em = datetime.utcnow()
    session.add(c)
    session.commit()
    return {"status": c.status}
