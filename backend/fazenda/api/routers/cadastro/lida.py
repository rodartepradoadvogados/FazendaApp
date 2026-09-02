"""
Cadastro > Lida — tarefas gerais da fazenda que não são protocolo de animal
(limpar cocho, acompanhar obra...). Sem Tipo produtivo/reprodutivo/sanitário
— ver fazenda/models/lida.py para a diferença em relação ao Protocolo
Customizado. Mesmo padrão de CRUD de cadastro/protocolos_customizados.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import Lida, LidaEtapa, LidaLancamento
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter()

MODOS_LIDA = ["periodo", "frequencia"]


class EtapaLidaIn(BaseModel):
    dia_inicio: int
    dia_fim: int | None = None  # None = etapa de um dia só; preenchido = repete todo dia até lá
    descricao_evento: str
    insumo_padrao: str | None = None
    insumo_dose: float | None = None
    insumo_unidade: str | None = None
    foto_obrigatoria: bool = False
    ordem: int = 0


class LidaIn(BaseModel):
    nome: str
    modo: str = "periodo"
    dia_inicial: int = 0  # modo "periodo"
    # modo "frequencia" — uma única tarefa que se repete
    frequencia_dias: int | None = None
    descricao_evento: str | None = None
    insumo_padrao: str | None = None
    insumo_dose: float | None = None
    insumo_unidade: str | None = None
    foto_obrigatoria: bool = False
    # comportamento na confirmação — vale para os dois modos
    dar_baixa_estoque: bool = False
    vincular_financeiro: bool = False
    observacao: str | None = None
    ativo: bool = True
    etapas: list[EtapaLidaIn] = []  # só usado no modo "periodo"


def _validar(dados: LidaIn) -> None:
    if dados.modo not in MODOS_LIDA:
        raise HTTPException(status_code=400, detail=f"Modo inválido — use um de: {', '.join(MODOS_LIDA)}")
    if dados.modo == "frequencia":
        if not dados.frequencia_dias or dados.frequencia_dias <= 0:
            raise HTTPException(status_code=400, detail="Informe a cada quantos dias esta lida se repete")
        if not (dados.descricao_evento or "").strip():
            raise HTTPException(status_code=400, detail="Descreva o que fazer nesta lida")
        if dados.dar_baixa_estoque and not (dados.insumo_padrao and dados.insumo_dose and dados.insumo_unidade):
            raise HTTPException(
                status_code=400,
                detail="Para dar baixa no estoque, informe o produto, a dose e a unidade consumidos a cada confirmação.",
            )
        return
    # modo "periodo"
    if dados.dia_inicial not in (0, 1):
        raise HTTPException(status_code=400, detail="dia_inicial deve ser 0 ou 1")
    if not dados.etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa")
    for e in dados.etapas:
        if e.dia_inicio < 0:
            raise HTTPException(status_code=400, detail="O dia de uma etapa não pode ser negativo")
        if e.dia_fim is not None and e.dia_fim < e.dia_inicio:
            raise HTTPException(status_code=400, detail="O dia final de uma etapa não pode ser antes do dia inicial")
        if not (e.descricao_evento or "").strip():
            raise HTTPException(status_code=400, detail="Descreva o que fazer em cada etapa")
        if dados.dar_baixa_estoque and e.insumo_padrao and not (e.insumo_dose and e.insumo_unidade):
            raise HTTPException(
                status_code=400,
                detail=f'Para dar baixa no estoque, informe a dose e a unidade do insumo "{e.insumo_padrao}".',
            )


def _serializar(session: Session, l: Lida) -> dict:
    etapas = session.exec(
        select(LidaEtapa).where(LidaEtapa.lida_id == l.id).order_by(LidaEtapa.dia_inicio, LidaEtapa.ordem)
    ).all()
    if l.modo == "frequencia":
        duracao_dias = None
    else:
        fins = [e.dia_fim if e.dia_fim is not None else e.dia_inicio for e in etapas]
        duracao_dias = (max(fins) - l.dia_inicial) if fins else 0
    return {**l.model_dump(), "etapas": [e.model_dump() for e in etapas], "duracao_dias": duracao_dias}


@router.get("/lidas")
def listar_lidas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Lida).order_by(Lida.nome)
    if fazenda_id is not None:
        query = query.where(Lida.fazenda_id == fazenda_id)
    return [_serializar(session, l) for l in session.exec(query).all()]


@router.post("/lidas", status_code=201)
def criar_lida(
    dados: LidaIn, session: Session = Depends(get_session), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(Lida).where(Lida.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(Lida.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe uma lida com o nome '{nome}'")
    _validar(dados)

    lida = Lida(
        nome=nome, modo=dados.modo, dia_inicial=dados.dia_inicial if dados.modo == "periodo" else 0,
        frequencia_dias=dados.frequencia_dias if dados.modo == "frequencia" else None,
        descricao_evento=dados.descricao_evento if dados.modo == "frequencia" else None,
        insumo_padrao=dados.insumo_padrao if dados.modo == "frequencia" else None,
        insumo_dose=dados.insumo_dose if dados.modo == "frequencia" else None,
        insumo_unidade=dados.insumo_unidade if dados.modo == "frequencia" else None,
        foto_obrigatoria=dados.foto_obrigatoria if dados.modo == "frequencia" else False,
        dar_baixa_estoque=dados.dar_baixa_estoque, vincular_financeiro=dados.vincular_financeiro,
        observacao=dados.observacao, ativo=dados.ativo, fazenda_id=fazenda_id,
    )
    session.add(lida)
    session.commit()
    session.refresh(lida)
    if dados.modo == "periodo":
        for etapa in dados.etapas:
            session.add(LidaEtapa(lida_id=lida.id, fazenda_id=fazenda_id, **etapa.model_dump()))
        session.commit()
    return _serializar(session, lida)


@router.put("/lidas/{lida_id}")
def atualizar_lida(
    lida_id: int, dados: LidaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    lida = session.get(Lida, lida_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not lida or (fazenda_id is not None and lida.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lida não encontrada")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar(dados)

    lida.nome = nome
    lida.modo = dados.modo
    lida.dia_inicial = dados.dia_inicial if dados.modo == "periodo" else 0
    lida.frequencia_dias = dados.frequencia_dias if dados.modo == "frequencia" else None
    lida.descricao_evento = dados.descricao_evento if dados.modo == "frequencia" else None
    lida.insumo_padrao = dados.insumo_padrao if dados.modo == "frequencia" else None
    lida.insumo_dose = dados.insumo_dose if dados.modo == "frequencia" else None
    lida.insumo_unidade = dados.insumo_unidade if dados.modo == "frequencia" else None
    lida.foto_obrigatoria = dados.foto_obrigatoria if dados.modo == "frequencia" else False
    lida.dar_baixa_estoque = dados.dar_baixa_estoque
    lida.vincular_financeiro = dados.vincular_financeiro
    lida.observacao = dados.observacao
    lida.ativo = dados.ativo
    session.add(lida)

    etapas_antigas = session.exec(select(LidaEtapa).where(LidaEtapa.lida_id == lida_id)).all()
    for e in etapas_antigas:
        session.delete(e)
    session.commit()
    if dados.modo == "periodo":
        for etapa in dados.etapas:
            session.add(LidaEtapa(lida_id=lida.id, fazenda_id=fazenda_id, **etapa.model_dump()))
        session.commit()
    return _serializar(session, lida)


@router.delete("/lidas/{lida_id}")
def excluir_lida(
    lida_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    lida = session.get(Lida, lida_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not lida or (fazenda_id is not None and lida.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lida não encontrada")
    ja_lancada = session.exec(select(LidaLancamento).where(LidaLancamento.lida_id == lida_id)).first()
    if ja_lancada:
        raise HTTPException(
            status_code=409,
            detail="Esta lida já foi lançada ao menos uma vez e não pode ser excluída — desative-a em vez disso.",
        )
    etapas = session.exec(select(LidaEtapa).where(LidaEtapa.lida_id == lida_id)).all()
    for e in etapas:
        session.delete(e)
    session.delete(lida)
    session.commit()
    return {"excluido": True}
