"""
Central de Protocolos — abas Acompanhamento e Histórico: junta IATF, Indução
de Lactação, Sanitário e Customizado num único painel, com o mesmo formato de
linha (nome do lançamento já com a data — ver
fazenda.rules.nomenclatura_protocolo — tipo, progresso), filtrável por nome,
período e tipo (produtivo/reprodutivo/sanitario).

Isto é ADICIONAL — não substitui os relatórios específicos de cada domínio
(Histórico de Ciclos IATF em Reprodução, Protocolos Sanitários em Sanidade,
Relatório de Rastreabilidade Sanitária), que continuam nos mesmos lugares.

Sanitário é o único dos quatro sem um "cabeçalho de lote" (cada
ProtocoloSanitarioLancamento é por animal) — aqui ele é agrupado por
(protocolo_id, data_inicio) só para efeito de exibição, sem alterar o
modelo de dados.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    ProtocoloCustomizado, ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento,
    ProtocoloIatfAplicacao, ProtocoloIatfLancamento,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento,
    ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioLancamento,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento

router = APIRouter(prefix="/central-protocolos", tags=["central-protocolos"])


def _linha(*, tipo: str, origem: str, origem_id: int, nome: str, data_inicio: date, data_fim: date,
           etapas_total: int, etapas_realizadas: int, animais: int, ativo: bool = True) -> dict:
    if not ativo:
        status = "cancelado"
    elif etapas_total and etapas_realizadas == etapas_total:
        status = "concluido"
    else:
        status = "ativo"
    return {
        "tipo": tipo, "origem": origem, "origem_id": origem_id, "nome": nome,
        "data_inicio": data_inicio, "data_fim": data_fim,
        "etapas_total": etapas_total, "etapas_realizadas": etapas_realizadas,
        "etapas_faltam": max(etapas_total - etapas_realizadas, 0),
        "animais": animais, "status": status,
    }


def _linhas_iatf(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(ProtocoloIatfLancamento)
    if fazenda_id is not None:
        query = query.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[ProtocoloIatfAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)
    linhas = []
    for l in lancamentos:
        aps = por_lanc.get(l.id, [])
        datas = [a.data_prevista for a in aps]
        linhas.append(_linha(
            tipo="reprodutivo", origem="iatf", origem_id=l.id, nome=l.nome_protocolo,
            data_inicio=l.data_d0, data_fim=max(datas) if datas else l.data_d0,
            etapas_total=len(aps), etapas_realizadas=sum(1 for a in aps if a.realizada),
            animais=len({a.numero_matriz for a in aps}),
        ))
    return linhas


def _linhas_inducao(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(ProtocoloInducaoLancamento)
    if fazenda_id is not None:
        query = query.where(ProtocoloInducaoLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloInducaoAplicacao).where(ProtocoloInducaoAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[ProtocoloInducaoAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)
    linhas = []
    for l in lancamentos:
        aps = por_lanc.get(l.id, [])
        datas = [a.data_prevista for a in aps]
        linhas.append(_linha(
            tipo="produtivo", origem="inducao", origem_id=l.id, nome=l.nome_protocolo,
            data_inicio=l.data_d0, data_fim=max(datas) if datas else l.data_d0,
            etapas_total=len(aps), etapas_realizadas=sum(1 for a in aps if a.realizada),
            animais=len({a.numero_matriz for a in aps}),
        ))
    return linhas


def _linhas_customizado(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(ProtocoloCustomizadoLancamento)
    if fazenda_id is not None:
        query = query.where(ProtocoloCustomizadoLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    protocolos = {p.id: p for p in session.exec(select(ProtocoloCustomizado)).all()}
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloCustomizadoAplicacao).where(ProtocoloCustomizadoAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[ProtocoloCustomizadoAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)
    linhas = []
    for l in lancamentos:
        molde = protocolos.get(l.protocolo_id)
        tipo = molde.tipo if molde else None
        if not tipo:
            continue  # sem Tipo cadastrado -> continua na Agenda, fora destes filtros
        aps = por_lanc.get(l.id, [])
        datas = [a.data_prevista for a in aps]
        linhas.append(_linha(
            tipo=tipo, origem="customizado", origem_id=l.id, nome=l.nome_protocolo,
            data_inicio=l.data_inicio, data_fim=max(datas) if datas else l.data_inicio,
            etapas_total=len(aps), etapas_realizadas=sum(1 for a in aps if a.realizada),
            animais=len({a.numero_matriz for a in aps if a.numero_matriz}),
            ativo=l.ativo,
        ))
    return linhas


def _linhas_sanitario(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(ProtocoloSanitarioLancamento)
    if fazenda_id is not None:
        query = query.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []
    protocolos = {p.id: p for p in session.exec(select(ProtocoloSanitario)).all()}
    ids = [l.id for l in lancamentos]
    aplicacoes = session.exec(
        select(ProtocoloSanitarioAplicacao).where(ProtocoloSanitarioAplicacao.lancamento_id.in_(ids))
    ).all()
    por_lanc: dict[int, list[ProtocoloSanitarioAplicacao]] = defaultdict(list)
    for a in aplicacoes:
        por_lanc[a.lancamento_id].append(a)

    # Agrupa por (protocolo_id, data_inicio) — cada ProtocoloSanitarioLancamento
    # é por animal; aqui vira uma única linha "lote", só para exibição.
    grupos: dict[tuple[int, date], list[ProtocoloSanitarioLancamento]] = defaultdict(list)
    for l in lancamentos:
        grupos[(l.protocolo_id, l.data_inicio)].append(l)

    linhas = []
    for (protocolo_id, data_inicio), grupo in grupos.items():
        molde = protocolos.get(protocolo_id)
        nome_base = molde.nome if molde else "Protocolo Sanitário"
        aps_grupo: list[ProtocoloSanitarioAplicacao] = []
        for l in grupo:
            aps_grupo.extend(por_lanc.get(l.id, []))
        datas = [a.data_prevista for a in aps_grupo]
        dia_inicial = molde.dia_inicial if molde else 0
        dias_previstos = [(d - data_inicio).days + dia_inicial for d in datas] if datas else [dia_inicial]
        dia_final = max(dias_previstos) if dias_previstos else dia_inicial
        nome = gerar_nome_lancamento(nome_base, data_inicio, dia_inicial, dia_final)
        linhas.append(_linha(
            tipo="sanitario", origem="sanitario", origem_id=grupo[0].id, nome=nome,
            data_inicio=data_inicio, data_fim=max(datas) if datas else data_inicio,
            etapas_total=len(aps_grupo), etapas_realizadas=sum(1 for a in aps_grupo if a.realizada),
            animais=len({l.numero_matriz for l in grupo}),
        ))
    return linhas


def _todas_as_linhas(session: Session, fazenda_id: int | None) -> list[dict]:
    return (
        _linhas_iatf(session, fazenda_id)
        + _linhas_inducao(session, fazenda_id)
        + _linhas_sanitario(session, fazenda_id)
        + _linhas_customizado(session, fazenda_id)
    )


def _filtrar(linhas: list[dict], *, nome: str | None, tipo: str | None,
             data_de: date | None, data_ate: date | None) -> list[dict]:
    if nome:
        alvo = nome.strip().lower()
        linhas = [l for l in linhas if alvo in l["nome"].lower()]
    if tipo:
        linhas = [l for l in linhas if l["tipo"] == tipo]
    if data_de:
        linhas = [l for l in linhas if l["data_fim"] >= data_de]
    if data_ate:
        linhas = [l for l in linhas if l["data_inicio"] <= data_ate]
    return sorted(linhas, key=lambda l: l["data_inicio"], reverse=True)


@router.get("/acompanhamento")
def acompanhamento(
    nome: str | None = None, tipo: str | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Protocolos EM ANDAMENTO (ao menos uma etapa pendente) dos 4 tipos, juntos."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    linhas = _todas_as_linhas(session, fazenda_id)
    linhas = [l for l in linhas if l["status"] == "ativo"]
    return _filtrar(linhas, nome=nome, tipo=tipo, data_de=None, data_ate=None)


@router.get("/historico")
def historico(
    nome: str | None = None, tipo: str | None = None,
    data_de: date | None = None, data_ate: date | None = None,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Concluídos e cancelados dos 4 tipos, juntos — para consulta/exportação."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    linhas = _todas_as_linhas(session, fazenda_id)
    linhas = [l for l in linhas if l["status"] in ("concluido", "cancelado")]
    return _filtrar(linhas, nome=nome, tipo=tipo, data_de=data_de, data_ate=data_ate)
