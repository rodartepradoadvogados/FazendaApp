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
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, exigir_pode_publicar, get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import LancamentoPendente, Usuario
from fazenda.rules import telegram_fluxos as fx
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/aprovacoes", tags=["aprovacoes"])


def _exigir_permissao_do_tipo(p: LancamentoPendente, user: Usuario) -> None:
    """Pendente de matéria do blog (tipo "noticia_manual", ver
    POST /news/manual) exige a mesma permissão de publicar matérias
    (Usuario.pode_publicar_materias_blog) de tudo mais em News — não basta
    ser admin, senão qualquer admin aprovaria matéria do blog por aqui."""
    if p.tipo == "noticia_manual":
        exigir_pode_publicar(user)


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
def listar_pendentes(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Lançamentos aguardando aprovação, do mais novo para o mais antigo."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(LancamentoPendente).where(LancamentoPendente.status == "pendente")
    if fazenda_id is not None:
        query = query.where(LancamentoPendente.fazenda_id.in_((fazenda_id, None)))
    pend = session.exec(query.order_by(LancamentoPendente.criado_em.desc())).all()
    return [_dto(p) for p in pend]


@router.get("/contagem", dependencies=[Depends(exigir_admin)])
def contar_pendentes(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Quantidade de pendências (para o sininho de notificações)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(LancamentoPendente).where(LancamentoPendente.status == "pendente")
    if fazenda_id is not None:
        query = query.where(LancamentoPendente.fazenda_id.in_((fazenda_id, None)))
    total = len(session.exec(query).all())
    return {"pendentes": total}


class EditarPendenteIn(BaseModel):
    dados: dict


def _verificar_posse(p: LancamentoPendente, fazenda_id: int | None) -> None:
    """LancamentoPendente é criado pelo bot do Telegram, que ainda não sabe
    associar o chat a uma fazenda (ponto cego fora do escopo deste retrofit)
    — por isso trata fazenda_id=None como "legado", não bloqueia. Só bloqueia
    quando o pendente JÁ tem uma fazenda gravada e é de outra."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is not None and p.fazenda_id not in (None, fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento pendente não encontrado")


@router.put("/{pendente_id}")
def editar(
    pendente_id: int, entrada: EditarPendenteIn, session: Session = Depends(get_session),
    user: Usuario = Depends(exigir_admin), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Corrige os dados de um lançamento pendente antes de aprovar (ex.: trocar
    uma unidade digitada errada). Só enquanto está pendente."""
    p = session.get(LancamentoPendente, pendente_id)
    if not p:
        raise HTTPException(status_code=404, detail="Lançamento pendente não encontrado")
    _verificar_posse(p, fazenda_id)
    _exigir_permissao_do_tipo(p, user)
    if p.status != "pendente":
        raise HTTPException(status_code=409, detail=f"Este lançamento já está {p.status}.")
    p.payload = json.dumps(entrada.dados)
    p.resumo = fx.montar_resumo(p.tipo, entrada.dados)
    p.erro = None
    session.add(p)
    session.commit()
    return _dto(p)


@router.post("/{pendente_id}/aprovar")
def aprovar(
    pendente_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Aprova e MATERIALIZA o lançamento — cria o registro real. Se a criação
    falhar (ex.: animal inexistente), guarda o erro e mantém como pendente."""
    p = session.get(LancamentoPendente, pendente_id)
    if not p:
        raise HTTPException(status_code=404, detail="Lançamento pendente não encontrado")
    _verificar_posse(p, fazenda_id)
    _exigir_permissao_do_tipo(p, user)
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
def rejeitar(
    pendente_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Rejeita o lançamento — não cria nada."""
    p = session.get(LancamentoPendente, pendente_id)
    if not p:
        raise HTTPException(status_code=404, detail="Lançamento pendente não encontrado")
    _verificar_posse(p, fazenda_id)
    _exigir_permissao_do_tipo(p, user)
    if p.status != "pendente":
        raise HTTPException(status_code=409, detail=f"Este lançamento já está {p.status}.")
    p.status = "rejeitado"
    p.decidido_em = datetime.utcnow()
    p.decidido_por = user.username
    session.add(p)
    session.commit()
    return {"rejeitado": True}
