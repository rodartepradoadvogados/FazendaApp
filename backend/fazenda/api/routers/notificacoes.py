"""
Router de notificações — agrega, para o dia atual, tudo que é relevante para
o usuário logado (eventos da agenda, contas a pagar, pendências de exclusão),
filtrando por módulo/permissão. Alimenta o sininho fixo do topo.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.api.routers.agenda import calcular_agenda
from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import SolicitacaoExclusao, Usuario

router = APIRouter(prefix="/notificacoes", tags=["notificacoes"])


@router.get("/")
def notificacoes_hoje(
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    hoje = date.today()
    itens: list[dict] = []

    # calcular_agenda já filtra os eventos pela permissão do usuário (ver
    # MODULO_POR_CATEGORIA em agenda.py) — não precisa repetir o filtro aqui.
    agenda = calcular_agenda(data=hoje, dias=0, session=session, usuario=user)
    for e in agenda["eventos"]:
        if e["data"] != hoje.isoformat():
            continue
        itens.append({
            "tipo": "agenda",
            "categoria": e["categoria"],
            "descricao": e["descricao"],
            "numero_animal": e["numero_animal"],
            "cor": e["cor"],
        })

    if user.papel == "admin":
        pendentes = session.exec(
            select(SolicitacaoExclusao).where(SolicitacaoExclusao.status == "pendente")
        ).all()
        for p in pendentes:
            itens.append({
                "tipo": "exclusao_pendente",
                "categoria": "Aprovação pendente",
                "descricao": f"Exclusão de {p.titulo or f'{p.tipo} #{p.id_alvo}'} — solicitada por {p.solicitado_por or '—'}",
                "numero_animal": None,
                "cor": "var(--amber)",
            })

    return {"itens": itens, "total": len(itens)}
