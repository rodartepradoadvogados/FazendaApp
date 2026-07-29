"""
Cadastro > Protocolos personalizados — motor de protocolos configurável pelo
usuário: um molde genérico de "dia + evento + insumo padrão", sem hormônios,
medicamentos ou implante específicos (ver ProtocoloIatf*/ProtocoloSanitario*/
ProtocoloInducao* para esses casos específicos, que continuam intactos).

Mesmo padrão de CRUD de fazenda/api/routers/cadastro/protocolos_sanitarios.py
(GET lista, POST cria com 409 em nome duplicado, PUT substitui as etapas por
completo). DELETE aqui é exclusivo desta família: recusa (409) se já houver
lançamento, para nunca apagar histórico.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import ProtocoloCustomizado, ProtocoloCustomizadoEtapa, ProtocoloCustomizadoLancamento
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter()

# Whitelist fechada de propósito: a categoria do template vira a categoria do
# evento na Agenda (ver MODULO_POR_CATEGORIA em api/routers/agenda.py), que
# decide quem tem permissão de VER o evento. Uma categoria fora da lista
# devolveria "nenhum módulo exigido" e vazaria o evento para todo mundo.
# "alimentacao" fica fora de propósito: a Agenda sequestra a célula de ação
# dessa categoria para "Ir para Dieta" em vez do botão normal de realizado.
CATEGORIAS_PROTOCOLO_CUSTOM = ["Atividades", "Reprodutivo", "Produção", "sanidade", "Rebanho", "Gestão/Financeiro"]
VIAS_APLICACAO = ["Intramuscular", "Subcutânea", "Intravenosa", "Intramamária", "Oral", "Tópica", "Subdérmica", "Intrauterina"]


class EtapaCustomizadaIn(BaseModel):
    dia: int
    descricao_evento: str
    insumo_padrao: str | None = None
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None
    observacao: str | None = None
    ordem: int = 0


class ProtocoloCustomizadoIn(BaseModel):
    nome: str
    categoria: str = "Atividades"
    dia_inicial: int = 0
    observacao: str | None = None
    ativo: bool = True
    etapas: list[EtapaCustomizadaIn]


def _validar(dados: ProtocoloCustomizadoIn) -> None:
    if dados.categoria not in CATEGORIAS_PROTOCOLO_CUSTOM:
        raise HTTPException(status_code=400, detail=f"Categoria inválida — use uma de: {', '.join(CATEGORIAS_PROTOCOLO_CUSTOM)}")
    if dados.dia_inicial not in (0, 1):
        raise HTTPException(status_code=400, detail="dia_inicial deve ser 0 ou 1")
    if not dados.etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa do protocolo")
    for e in dados.etapas:
        if e.dia < 0:
            raise HTTPException(status_code=400, detail="O dia de uma etapa não pode ser negativo")
        if not (e.descricao_evento or "").strip():
            raise HTTPException(status_code=400, detail="Informe a descrição do evento de cada etapa")
        if e.via and e.via not in VIAS_APLICACAO:
            raise HTTPException(status_code=400, detail=f"Via inválida — use uma de: {', '.join(VIAS_APLICACAO)}")
        if e.dose is not None and e.dose <= 0:
            raise HTTPException(status_code=400, detail="A dose de uma etapa deve ser positiva")


def _serializar(session: Session, p: ProtocoloCustomizado) -> dict:
    etapas = session.exec(
        select(ProtocoloCustomizadoEtapa)
        .where(ProtocoloCustomizadoEtapa.protocolo_id == p.id)
        .order_by(ProtocoloCustomizadoEtapa.dia, ProtocoloCustomizadoEtapa.ordem)
    ).all()
    dias = [e.dia for e in etapas]
    duracao_dias = (max(dias) - p.dia_inicial) if dias else 0
    return {**p.model_dump(), "etapas": [e.model_dump() for e in etapas], "duracao_dias": duracao_dias}


@router.get("/protocolos-customizados")
def listar_protocolos_customizados(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ProtocoloCustomizado).order_by(ProtocoloCustomizado.nome)
    if fazenda_id is not None:
        query = query.where(ProtocoloCustomizado.fazenda_id == fazenda_id)
    protocolos = session.exec(query).all()
    return [_serializar(session, p) for p in protocolos]


@router.post("/protocolos-customizados", status_code=201)
def criar_protocolo_customizado(
    dados: ProtocoloCustomizadoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(ProtocoloCustomizado).where(ProtocoloCustomizado.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(ProtocoloCustomizado.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe um protocolo personalizado com o nome '{nome}'")
    _validar(dados)

    protocolo = ProtocoloCustomizado(
        nome=nome, categoria=dados.categoria, dia_inicial=dados.dia_inicial,
        observacao=dados.observacao, ativo=dados.ativo, fazenda_id=fazenda_id,
    )
    session.add(protocolo)
    session.commit()
    session.refresh(protocolo)
    for etapa in dados.etapas:
        session.add(ProtocoloCustomizadoEtapa(protocolo_id=protocolo.id, fazenda_id=fazenda_id, **etapa.model_dump()))
    session.commit()
    return _serializar(session, protocolo)


@router.put("/protocolos-customizados/{protocolo_id}")
def atualizar_protocolo_customizado(
    protocolo_id: int, dados: ProtocoloCustomizadoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    protocolo = session.get(ProtocoloCustomizado, protocolo_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar(dados)

    protocolo.nome = nome
    protocolo.categoria = dados.categoria
    protocolo.dia_inicial = dados.dia_inicial
    protocolo.observacao = dados.observacao
    protocolo.ativo = dados.ativo
    session.add(protocolo)

    etapas_antigas = session.exec(
        select(ProtocoloCustomizadoEtapa).where(ProtocoloCustomizadoEtapa.protocolo_id == protocolo_id)
    ).all()
    for e in etapas_antigas:
        session.delete(e)
    session.commit()
    for etapa in dados.etapas:
        session.add(ProtocoloCustomizadoEtapa(protocolo_id=protocolo.id, fazenda_id=fazenda_id, **etapa.model_dump()))
    session.commit()
    return _serializar(session, protocolo)


@router.delete("/protocolos-customizados/{protocolo_id}")
def excluir_protocolo_customizado(
    protocolo_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    protocolo = session.get(ProtocoloCustomizado, protocolo_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    ja_lancado = session.exec(
        select(ProtocoloCustomizadoLancamento).where(ProtocoloCustomizadoLancamento.protocolo_id == protocolo_id)
    ).first()
    if ja_lancado:
        raise HTTPException(
            status_code=409,
            detail="Este protocolo já foi lançado ao menos uma vez e não pode ser excluído — desative-o em vez disso.",
        )
    etapas = session.exec(
        select(ProtocoloCustomizadoEtapa).where(ProtocoloCustomizadoEtapa.protocolo_id == protocolo_id)
    ).all()
    for e in etapas:
        session.delete(e)
    session.delete(protocolo)
    session.commit()
    return {"excluido": True}
