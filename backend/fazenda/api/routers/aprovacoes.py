"""
Fila de aprovação dos lançamentos operacionais enviados pelo Telegram.

A conta principal (admin) vê aqui os lançamentos pendentes (pesagem, parto,
secagem, troca de lote, etc.), com um resumo, e decide APROVAR (o registro é
criado de verdade no sistema, pela mesma lógica do site) ou REJEITAR.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user
from fazenda.database import get_session
from fazenda.models import LancamentoPendente, Usuario
from fazenda.rules import telegram_fluxos as fx

router = APIRouter(prefix="/aprovacoes", tags=["aprovacoes"])


def _dto(p: LancamentoPendente) -> dict:
    fluxo = fx.FLUXOS.get(p.tipo, {})
    return {
        "id": p.id,
        "tipo": p.tipo,
        "rotulo": fluxo.get("rotulo", p.tipo),
        "resumo": p.resumo,
        "dados": json.loads(p.payload or "{}"),
        "status": p.status,
        "erro": p.erro,
        "solicitante_nome": p.solicitante_nome,
        "solicitante_chat_id": p.solicitante_chat_id,
        "criado_em": p.criado_em.isoformat() if p.criado_em else None,
        "decidido_em": p.decidido_em.isoformat() if p.decidido_em else None,
        "decidido_por": p.decidido_por,
    }


@router.get("", dependencies=[Depends(exigir_admin)])
@router.get("/", dependencies=[Depends(exigir_admin)])
def listar_pendentes(session: Session = Depends(get_session)) -> list[dict]:
    """Lançamentos aguardando aprovação, do mais novo para o mais antigo."""
    pend = session.exec(
        select(LancamentoPendente)
        .where(LancamentoPendente.status == "pendente")
        .order_by(LancamentoPendente.criado_em.desc())
    ).all()
    return [_dto(p) for p in pend]


@router.get("/contagem", dependencies=[Depends(exigir_admin)])
def contar_pendentes(session: Session = Depends(get_session)) -> dict:
    """Quantidade de pendências (para o sininho de notificações)."""
    total = len(session.exec(select(LancamentoPendente).where(LancamentoPendente.status == "pendente")).all())
    return {"pendentes": total}


@router.post("/{pendente_id}/aprovar")
def aprovar(pendente_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)) -> dict:
    """Aprova e MATERIALIZA o lançamento — cria o registro real. Se a criação
    falhar (ex.: animal inexistente), guarda o erro e mantém como pendente."""
    p = session.get(LancamentoPendente, pendente_id)
    if not p:
        raise HTTPException(status_code=404, detail="Lançamento pendente não encontrado")
    if p.status != "pendente":
        raise HTTPException(status_code=409, detail=f"Este lançamento já está {p.status}.")

    try:
        resultado = fx.criar_registro(p.tipo, json.loads(p.payload or "{}"), session)
    except HTTPException as e:
        p.erro = str(e.detail)
        session.add(p)
        session.commit()
        raise HTTPException(status_code=400, detail=f"Não foi possível criar o lançamento: {e.detail}")
    except Exception as e:  # noqa: BLE001
        p.erro = str(e)
        session.add(p)
        session.commit()
        raise HTTPException(status_code=400, detail=f"Não foi possível criar o lançamento: {e}")

    p.status = "aprovado"
    p.erro = None
    p.decidido_em = datetime.utcnow()
    p.decidido_por = user.username
    session.add(p)
    session.commit()
    return {"aprovado": True, "resultado": resultado}


@router.post("/{pendente_id}/rejeitar")
def rejeitar(pendente_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin)) -> dict:
    """Rejeita o lançamento — não cria nada."""
    p = session.get(LancamentoPendente, pendente_id)
    if not p:
        raise HTTPException(status_code=404, detail="Lançamento pendente não encontrado")
    if p.status != "pendente":
        raise HTTPException(status_code=409, detail=f"Este lançamento já está {p.status}.")
    p.status = "rejeitado"
    p.decidido_em = datetime.utcnow()
    p.decidido_por = user.username
    session.add(p)
    session.commit()
    return {"rejeitado": True}
