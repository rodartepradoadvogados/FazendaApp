"""
Router de Protocolos personalizados — lançar/listar ativos/cancelar. O
cadastro do molde (template) vive em
fazenda/api/routers/cadastro/protocolos_customizados.py; aqui só o que
acontece depois de o molde existir: aplicar contra animais/lote/fazenda,
o que materializa as aplicações que a Agenda lê (ver
fazenda/rules/protocolo_customizado.py::eventos_agenda).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import Usuario, get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    ProtocoloCustomizado, ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoEtapa, ProtocoloCustomizadoLancamento,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro

router = APIRouter(prefix="/protocolos-customizados", tags=["protocolos-customizados"])


def _texto_dia(etapas_dia: list[ProtocoloCustomizadoEtapa], campo: str, sep: str) -> str | None:
    partes = []
    for e in etapas_dia:
        valor = getattr(e, campo)
        if not valor:
            continue
        if campo == "insumo_padrao" and e.dose:
            partes.append(f"{valor} ({e.dose} {e.unidade or ''})".strip())
        else:
            partes.append(valor)
    return sep.join(partes) or None


@router.get("")
def listar_protocolos_para_lancar(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Protocolos ativos disponíveis para lançamento (o cadastro/edição vive em
    Configurações > Cadastro > Protocolos personalizados)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ProtocoloCustomizado).where(ProtocoloCustomizado.ativo == True).order_by(ProtocoloCustomizado.nome)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(ProtocoloCustomizado.fazenda_id == fazenda_id)
    protocolos = session.exec(query).all()
    out = []
    for p in protocolos:
        etapas = session.exec(
            select(ProtocoloCustomizadoEtapa)
            .where(ProtocoloCustomizadoEtapa.protocolo_id == p.id)
            .order_by(ProtocoloCustomizadoEtapa.dia, ProtocoloCustomizadoEtapa.ordem)
        ).all()
        ultimo_dia = max((e.dia for e in etapas), default=p.dia_inicial)
        out.append({**p.model_dump(), "etapas": [e.model_dump() for e in etapas], "duracao_dias": ultimo_dia - p.dia_inicial})
    return out


class LancarProtocoloCustomizadoIn(BaseModel):
    protocolo_id: int
    animais: list[str] = []  # vazio = tarefa da fazenda, sem animal específico
    lote: str | None = None  # rótulo informativo
    data_inicio: date
    responsavel: str | None = None
    observacao: str | None = None


@router.post("/lancar", status_code=201)
def lancar_protocolo_customizado(
    dados: LancarProtocoloCustomizadoIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    protocolo = session.get(ProtocoloCustomizado, dados.protocolo_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo personalizado não encontrado")
    if not protocolo.ativo:
        raise HTTPException(status_code=400, detail="Este protocolo está inativo")

    etapas = session.exec(
        select(ProtocoloCustomizadoEtapa)
        .where(ProtocoloCustomizadoEtapa.protocolo_id == dados.protocolo_id)
        .order_by(ProtocoloCustomizadoEtapa.dia, ProtocoloCustomizadoEtapa.ordem)
    ).all()
    if not etapas:
        raise HTTPException(status_code=400, detail="Este protocolo não tem etapas cadastradas")

    animais = [n.strip() for n in dados.animais if n.strip()]

    etapas_por_dia: dict[int, list[ProtocoloCustomizadoEtapa]] = {}
    for e in etapas:
        etapas_por_dia.setdefault(e.dia, []).append(e)

    lancamento = ProtocoloCustomizadoLancamento(
        protocolo_id=protocolo.id, nome_protocolo=protocolo.nome, categoria=protocolo.categoria,
        dia_inicial=protocolo.dia_inicial, data_inicio=dados.data_inicio, lote=dados.lote,
        responsavel=dados.responsavel, observacao=dados.observacao,
        usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
    )
    session.add(lancamento)
    session.commit()
    session.refresh(lancamento)

    eventos_criados = 0
    for dia, etapas_dia in etapas_por_dia.items():
        descricao = _texto_dia(etapas_dia, "descricao_evento", " + ")
        insumo = _texto_dia(etapas_dia, "insumo_padrao", " + ")
        observacao_dia = _texto_dia(etapas_dia, "observacao", " / ")
        data_prevista = dados.data_inicio + timedelta(days=dia - protocolo.dia_inicial)

        # Sem animais: uma única tarefa da fazenda por dia (ex.: calendário de
        # vacina do rebanho, sem animal específico).
        alvos = animais or [None]
        for numero in alvos:
            session.add(ProtocoloCustomizadoAplicacao(
                lancamento_id=lancamento.id, numero_matriz=numero, dia=dia,
                descricao=descricao or "Executar etapa do protocolo", insumo=insumo, observacao=observacao_dia,
                data_prevista=data_prevista, fazenda_id=fazenda_id,
            ))
            eventos_criados += 1

    session.commit()
    return {"criado": True, "lancamento_id": lancamento.id, "eventos_criados": eventos_criados, "animais": len(animais)}


@router.get("/ativos")
def listar_ativos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Lançamentos ativos com pelo menos uma aplicação pendente — para ver de
    relance o que está em andamento e poder cancelar."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ProtocoloCustomizadoLancamento).where(ProtocoloCustomizadoLancamento.ativo == True).order_by(  # noqa: E712
        ProtocoloCustomizadoLancamento.data_inicio.desc()
    )
    if fazenda_id is not None:
        query = query.where(ProtocoloCustomizadoLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    if not lancamentos:
        return []

    aplicacoes = session.exec(
        select(ProtocoloCustomizadoAplicacao).where(
            ProtocoloCustomizadoAplicacao.lancamento_id.in_(tuple(l.id for l in lancamentos))
        )
    ).all()
    por_lancamento: dict[int, list[ProtocoloCustomizadoAplicacao]] = {}
    for ap in aplicacoes:
        por_lancamento.setdefault(ap.lancamento_id, []).append(ap)

    ativos = []
    for lanc in lancamentos:
        aps = por_lancamento.get(lanc.id, [])
        pendentes = [a for a in aps if not a.realizada]
        if not pendentes:
            continue
        animais = sorted({a.numero_matriz for a in aps if a.numero_matriz}, key=chave_numero)
        proxima = min(pendentes, key=lambda a: a.dia)
        ativos.append({
            "lancamento_id": lanc.id,
            "nome_protocolo": lanc.nome_protocolo,
            "categoria": lanc.categoria,
            "data_inicio": lanc.data_inicio.isoformat(),
            "lote": lanc.lote,
            "responsavel": lanc.responsavel,
            "total_etapas": len(aps),
            "pendentes": len(pendentes),
            "animais": animais,
            "proxima_etapa": f"D{proxima.dia - lanc.dia_inicial}",
            "proxima_data": proxima.data_prevista.isoformat(),
        })
    return ativos


@router.post("/{lancamento_id}/cancelar")
def cancelar_lancamento(
    lancamento_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Cancela (soft-delete) um lançamento — as pendências saem da Agenda; o
    histórico (inclusive etapas já confirmadas) permanece no banco."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = session.get(ProtocoloCustomizadoLancamento, lancamento_id)
    if not lancamento or (fazenda_id is not None and lancamento.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    lancamento.ativo = False
    session.add(lancamento)
    session.commit()
    return {"cancelado": True}
