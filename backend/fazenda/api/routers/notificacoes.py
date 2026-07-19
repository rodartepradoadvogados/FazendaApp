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
from fazenda.models import PortalMensagem, SolicitacaoExclusao, Usuario

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

    # Portal > Comunicação: mensagens/tarefas recebidas que ainda não
    # desapareceram (ver regra de permanência em PortalMensagem).
    portal_pendentes = session.exec(
        select(PortalMensagem).where(
            PortalMensagem.destinatario_usuario_id == user.id,
            PortalMensagem.resolvida == False,  # noqa: E712
        )
    ).all()
    for m in portal_pendentes:
        if m.lida and not m.pede_retorno:
            continue
        remetente = session.get(Usuario, m.remetente_usuario_id)
        remetente_nome = (remetente.nome or remetente.username) if remetente else "—"
        if m.tipo == "tarefa":
            descricao = f"Tarefa de {remetente_nome}: {m.corpo}"
        else:
            descricao = f"Mensagem de {remetente_nome}" + (f" ({m.aba})" if m.aba else "") + f": {m.corpo}"
        itens.append({
            "tipo": "portal_mensagem",
            "categoria": "Portal",
            "descricao": descricao,
            "numero_animal": None,
            "cor": "var(--mob-vinho-fixo)" if m.tipo == "tarefa" else "var(--blue)",
            "portal_mensagem_id": m.id,
            "pede_retorno": m.pede_retorno,
        })

    return {"itens": itens, "total": len(itens)}
