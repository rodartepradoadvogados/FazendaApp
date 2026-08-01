"""
Router da Farmácia — o estoque de medicamentos/hormônios/vacinas organizado pela
hierarquia PRINCÍPIO ATIVO → marcas comerciais → apresentações (itens de
estoque). Expõe a visão gerencial unificada (somatório por princípio, mínimo por
apresentações, alerta de "inicializar estoque") e os utilitários usados no
curral: listar apresentações para o menu "qual frasco você está usando?" e
registrar o estoque inicial/primeira compra (gatilho de comunicação).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Doenca, Estoque, IndicacaoTerapeutica, MedicamentoComercial, MovimentoEstoque, PrincipioAtivo
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.farmacia import resumo_principios

router = APIRouter(prefix="/farmacia", tags=["farmacia"])


@router.get("/principios")
def listar_principios(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Visão gerencial completa: princípio → total unificado, apresentações,
    mínimo/alerta e a lista de itens de estoque (marcas/tamanhos)."""
    return resumo_principios(session, fazenda_id_seguro(fazenda_id))


@router.get("/principios/{principio_id}")
def detalhar_principio(
    principio_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pa = session.get(PrincipioAtivo, principio_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Princípio ativo não encontrado")
    resumo = next((r for r in resumo_principios(session, fazenda_id) if r["id"] == principio_id), None)
    marcas = session.exec(
        select(MedicamentoComercial).where(MedicamentoComercial.principio_ativo_id == principio_id)
        .order_by(MedicamentoComercial.nome_comercial)
    ).all()
    return {**(resumo or {}), "marcas": [m.model_dump() for m in marcas]}


class PrincipioIn(BaseModel):
    nome: str
    ativo: bool = True
    categoria_software: str | None = None
    uso_principal: str | None = None
    justificativa: str | None = None
    doenca_id: int | None = None
    eh_biologico: bool = False
    unidade_base: str | None = None
    unidade_apresentacao: str | None = None
    estoque_minimo_apresentacoes: float = 1.0


@router.post("/principios", status_code=201)
def criar_principio(
    dados: PrincipioIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(PrincipioAtivo).where(PrincipioAtivo.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(PrincipioAtivo.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe o princípio ativo '{nome}'")
    pa = PrincipioAtivo(**{**dados.model_dump(), "nome": nome, "fazenda_id": fazenda_id})
    session.add(pa)
    session.commit()
    session.refresh(pa)
    return pa.model_dump()


@router.put("/principios/{principio_id}")
def atualizar_principio(
    principio_id: int, dados: PrincipioIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pa = session.get(PrincipioAtivo, principio_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Princípio ativo não encontrado")
    for k, v in dados.model_dump().items():
        setattr(pa, k, v)
    session.add(pa)
    session.commit()
    session.refresh(pa)
    return pa.model_dump()


class MarcaIn(BaseModel):
    principio_ativo_id: int
    nome_comercial: str
    laboratorio: str | None = None
    ativo: bool = True


@router.post("/medicamentos", status_code=201)
def criar_marca(
    dados: MarcaIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome_comercial.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome comercial é obrigatório")
    pa = session.get(PrincipioAtivo, dados.principio_ativo_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=400, detail="Princípio ativo inexistente")
    existe = session.exec(
        select(MedicamentoComercial).where(
            MedicamentoComercial.principio_ativo_id == dados.principio_ativo_id,
            MedicamentoComercial.nome_comercial == nome,
        )
    ).first()
    if existe:
        raise HTTPException(status_code=409, detail=f"'{nome}' já está cadastrado neste princípio")
    m = MedicamentoComercial(**{**dados.model_dump(), "nome_comercial": nome, "fazenda_id": fazenda_id})
    session.add(m)
    session.commit()
    session.refresh(m)
    return m.model_dump()


@router.put("/medicamentos/{marca_id}")
def atualizar_marca(
    marca_id: int, dados: MarcaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    m = session.get(MedicamentoComercial, marca_id)
    if not m or (fazenda_id is not None and m.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    for k, v in dados.model_dump().items():
        setattr(m, k, v)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m.model_dump()


@router.delete("/medicamentos/{marca_id}")
def excluir_marca(
    marca_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    m = session.get(MedicamentoComercial, marca_id)
    if not m or (fazenda_id is not None and m.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    session.delete(m)
    session.commit()
    return {"ok": True}


@router.get("/apresentacoes")
def listar_apresentacoes(
    principio_ativo_id: int | None = None, produto: str | None = None, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Apresentações (frascos/potes) em estoque de um princípio — alimenta o menu
    "qual frasco você está usando?" no lançamento da aplicação. Pode filtrar pelo
    princípio ou pelo nome de um produto (deriva o princípio dele).

    Restrito à fazenda atual: sem o filtro, o menu listava os frascos de TODAS as
    fazendas, expondo o estoque de uma cliente para outra."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pa_id = principio_ativo_id
    if pa_id is None and produto:
        query_produto = select(Estoque).where(Estoque.nome == produto)
        if fazenda_id is not None:
            query_produto = query_produto.where(Estoque.fazenda_id == fazenda_id)
        item = session.exec(query_produto).first()
        pa_id = item.principio_ativo_id if item else None
    if pa_id is None:
        return []
    query_itens = select(Estoque).where(Estoque.principio_ativo_id == pa_id)
    if fazenda_id is not None:
        query_itens = query_itens.where(Estoque.fazenda_id == fazenda_id)
    itens = session.exec(query_itens.order_by(Estoque.nome)).all()
    return [
        {
            "estoque_id": it.id, "nome": it.nome, "marca": it.laboratorio,
            "saldo": it.quantidade or 0, "unidade": it.unidade,
            "volume_por_apresentacao": it.volume_por_apresentacao, "volume_unidade": it.volume_unidade,
            "estoque_inicializado": it.estoque_inicializado is not False,
        }
        for it in itens
    ]


class InicializarIn(BaseModel):
    quantidade: float
    data: date | None = None
    observacao: str | None = None


@router.post("/estoque/{estoque_id}/inicializar")
def inicializar_estoque(estoque_id: int, dados: InicializarIn, session: Session = Depends(get_session)) -> dict:
    """Registra o Estoque Inicial / Primeira Compra de um item: define o saldo,
    liga o gatilho (a partir daqui aplicações e dietas passam a dar baixa real) e
    grava o movimento para o histórico."""
    item = session.get(Estoque, estoque_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    if dados.quantidade < 0:
        raise HTTPException(status_code=400, detail="Quantidade não pode ser negativa")
    item.quantidade = dados.quantidade
    item.estoque_inicializado = True
    if item.estoque_minimo is not None:
        item.abaixo_minimo = (item.quantidade or 0) < item.estoque_minimo
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.add(MovimentoEstoque(
        nome_item=item.nome, movimento="Estoque inicial", quantidade=dados.quantidade,
        unidade=item.unidade, data_movimento=dados.data or date.today(),
        observacao=dados.observacao or "Estoque inicial — início do controle de baixas",
    ))
    session.commit()
    return {"ok": True, "estoque_inicializado": True, "quantidade": item.quantidade}


# ── Indicações terapêuticas (princípio ativo ↔ doença ↔ prioridade) ─────────
# Base do "substituto inteligente": gerenciado na edição do princípio ativo
# (Configurações > Cadastro > Sanitário > Princípio ativo), consultado por
# doença em GET /sanidade/indicacoes-doenca/{id}.
@router.get("/indicacoes")
def listar_indicacoes(
    principio_ativo_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.principio_ativo_id == principio_ativo_id)
    if fazenda_id is not None:
        query = query.where(IndicacaoTerapeutica.fazenda_id == fazenda_id)
    indicacoes = session.exec(query.order_by(IndicacaoTerapeutica.prioridade)).all()
    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    return [
        {"id": i.id, "doenca_id": i.doenca_id, "doenca": doencas.get(i.doenca_id, "—"), "prioridade": i.prioridade}
        for i in indicacoes
    ]


class IndicacaoIn(BaseModel):
    principio_ativo_id: int
    doenca_id: int
    prioridade: int = 2


@router.post("/indicacoes", status_code=201)
def criar_indicacao(
    dados: IndicacaoIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    pa = session.get(PrincipioAtivo, dados.principio_ativo_id)
    if not pa or (fazenda_id is not None and pa.fazenda_id != fazenda_id):
        raise HTTPException(status_code=400, detail="Princípio ativo inexistente")
    doenca = session.get(Doenca, dados.doenca_id)
    if not doenca or (fazenda_id is not None and doenca.fazenda_id != fazenda_id):
        raise HTTPException(status_code=400, detail="Doença inexistente")
    if dados.prioridade < 1:
        raise HTTPException(status_code=400, detail="Prioridade deve ser 1 ou maior")
    existe = session.exec(
        select(IndicacaoTerapeutica).where(
            IndicacaoTerapeutica.principio_ativo_id == dados.principio_ativo_id,
            IndicacaoTerapeutica.doenca_id == dados.doenca_id,
        )
    ).first()
    if existe:
        raise HTTPException(status_code=409, detail=f"'{pa.nome}' já está indicado para '{doenca.nome}'")
    ind = IndicacaoTerapeutica(**dados.model_dump(), fazenda_id=fazenda_id)
    session.add(ind)
    session.commit()
    session.refresh(ind)
    return {"id": ind.id, "doenca_id": ind.doenca_id, "doenca": doenca.nome, "prioridade": ind.prioridade}


@router.delete("/indicacoes/{indicacao_id}")
def excluir_indicacao(
    indicacao_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    ind = session.get(IndicacaoTerapeutica, indicacao_id)
    if not ind or (fazenda_id is not None and ind.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Indicação não encontrada")
    session.delete(ind)
    session.commit()
    return {"ok": True}
