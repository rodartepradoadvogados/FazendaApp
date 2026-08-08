"""
Cofre de acesso — visão consolidada (todas as fazendas-clientes) do acesso
de suporte da CowData: pedido → sessão → auditoria. Ver fazenda/models/
cofre_acesso.py para o modelo de dados e o racional do desenho.

Tudo aqui é `exigir_dono`-gated, mesmo padrão de painel_cowdata.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import criar_token, exigir_dono, token_manter_conectado
from fazenda.database import get_session
from fazenda.models import Fazenda, Usuario
from fazenda.models.cofre_acesso import (
    DURACAO_SESSAO_MINUTOS,
    MOTIVOS_ACESSO_SUPORTE,
    AuditoriaAcessoSuporte,
    PedidoAcessoSuporte,
    SessaoAcessoSuporte,
)

router = APIRouter(prefix="/painel-cowdata/cofre", tags=["cofre-acesso"])


def _nome_fazenda(session: Session, fazenda_id: int) -> str:
    f = session.get(Fazenda, fazenda_id)
    return f.nome if f else "?"


def _nome_usuario(session: Session, usuario_id: Optional[int]) -> Optional[str]:
    if not usuario_id:
        return None
    u = session.get(Usuario, usuario_id)
    return (u.nome or u.username) if u else None


@router.get("/motivos")
def listar_motivos(_: Usuario = Depends(exigir_dono)) -> list[str]:
    return MOTIVOS_ACESSO_SUPORTE


@router.get("/fazendas")
def listar_fazendas_cofre(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    """Fazendas-clientes elegíveis para pedido de acesso, com a política de
    aprovação de cada uma (exibida no formulário de solicitação)."""
    fazendas = session.exec(select(Fazenda).where(Fazenda.eh_empresa_cowdata == False)).all()  # noqa: E712
    return [{"id": f.id, "nome": f.nome, "exige_aprovacao_suporte": f.exige_aprovacao_suporte} for f in fazendas]


class PedidoAcessoIn(BaseModel):
    fazenda_id: int
    motivo: str


def _publico_pedido(session: Session, p: PedidoAcessoSuporte) -> dict:
    return {
        "id": p.id, "fazenda_id": p.fazenda_id, "fazenda_nome": _nome_fazenda(session, p.fazenda_id),
        "usuario_id": p.usuario_id, "solicitante_nome": _nome_usuario(session, p.usuario_id),
        "motivo": p.motivo, "status": p.status,
        "aprovador_nome": _nome_usuario(session, p.aprovado_por_usuario_id),
        "pedido_em": p.pedido_em.isoformat(), "decidido_em": p.decidido_em.isoformat() if p.decidido_em else None,
    }


def _publico_sessao(session: Session, s: SessaoAcessoSuporte) -> dict:
    agora = datetime.utcnow()
    segundos_restantes = (s.expira_em - agora).total_seconds()
    return {
        "id": s.id, "fazenda_id": s.fazenda_id, "fazenda_nome": _nome_fazenda(session, s.fazenda_id),
        "usuario_id": s.usuario_id, "membro_nome": _nome_usuario(session, s.usuario_id),
        "motivo": s.motivo, "iniciada_em": s.iniciada_em.isoformat(), "expira_em": s.expira_em.isoformat(),
        "encerrada_em": s.encerrada_em.isoformat() if s.encerrada_em else None,
        "ativa": s.encerrada_em is None and segundos_restantes > 0,
        "segundos_restantes": max(0, int(segundos_restantes)),
    }


def _abrir_sessao(session: Session, pedido: PedidoAcessoSuporte) -> SessaoAcessoSuporte:
    sessao = SessaoAcessoSuporte(
        pedido_id=pedido.id, fazenda_id=pedido.fazenda_id, usuario_id=pedido.usuario_id, motivo=pedido.motivo,
        expira_em=datetime.utcnow() + timedelta(minutes=DURACAO_SESSAO_MINUTOS),
    )
    session.add(sessao)
    session.add(AuditoriaAcessoSuporte(fazenda_id=pedido.fazenda_id, usuario_id=pedido.usuario_id, acao="entrada"))
    session.commit()
    session.refresh(sessao)
    return sessao


@router.post("/pedidos")
def solicitar_acesso(
    dados: PedidoAcessoIn, user: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
    manter_conectado: bool = Depends(token_manter_conectado),
) -> dict:
    fazenda = session.get(Fazenda, dados.fazenda_id)
    if not fazenda or fazenda.eh_empresa_cowdata:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    if dados.motivo not in MOTIVOS_ACESSO_SUPORTE:
        raise HTTPException(status_code=400, detail="Motivo inválido — escolha um da lista")

    pedido = PedidoAcessoSuporte(fazenda_id=dados.fazenda_id, usuario_id=user.id, motivo=dados.motivo)
    if not fazenda.exige_aprovacao_suporte:
        pedido.status = "aprovado"
        pedido.aprovado_por_usuario_id = user.id
        pedido.decidido_em = datetime.utcnow()
    session.add(pedido)
    session.commit()
    session.refresh(pedido)

    resultado = _publico_pedido(session, pedido)
    if pedido.status == "aprovado":
        sessao = _abrir_sessao(session, pedido)
        # Token novo, já com fid=fazenda + claim "suporte" — o frontend troca
        # o token guardado por este e navega pra dentro da fazenda; daqui pra
        # frente bloquear_em_modo_suporte (main.py) recusa ações destrutivas
        # até a sessão expirar (DURACAO_SESSAO_MINUTOS) ou ser encerrada.
        # Quando exige_aprovacao_suporte=True o pedido fica "aguardando" e
        # nenhum token é emitido aqui — só quando /pedidos/{id}/aprovar rodar
        # (ver limitação no docstring daquela rota).
        resultado["token"] = criar_token(
            user.username, fazenda_id=pedido.fazenda_id, suporte=True,
            sessao_suporte_id=sessao.id, manter_conectado=manter_conectado,
        )
        resultado["sessao_id"] = sessao.id
        resultado["sessao_expira_em"] = sessao.expira_em.isoformat()
    return resultado


@router.post("/pedidos/{pedido_id}/aprovar")
def aprovar_pedido(pedido_id: int, user: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    """LIMITAÇÃO CONHECIDA: ao contrário de solicitar_acesso (aprovação
    automática), esta rota não emite um token de suporte — quem aprova pode
    ser uma sessão/aba diferente de quem pediu, e o token pertence a quem vai
    ENTRAR na fazenda, não a quem aprova. Só importa quando
    Fazenda.exige_aprovacao_suporte=True (hoje nenhuma fazenda-piloto usa
    isso — default False, ver models/multitenant.py); quem pediu precisa
    recarregar/pedir de novo depois de aprovado para receber o token. Se essa
    trava vier a ser usada de verdade, vale revisitar (ex.: polling do
    solicitante pelo status do pedido, com o token vindo só quando "aprovado")."""
    pedido = session.get(PedidoAcessoSuporte, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if pedido.status != "aguardando_aprovacao":
        raise HTTPException(status_code=400, detail="Este pedido já foi decidido")
    pedido.status = "aprovado"
    pedido.aprovado_por_usuario_id = user.id
    pedido.decidido_em = datetime.utcnow()
    session.add(pedido)
    session.commit()
    session.refresh(pedido)
    _abrir_sessao(session, pedido)
    return _publico_pedido(session, pedido)


@router.post("/pedidos/{pedido_id}/negar")
def negar_pedido(pedido_id: int, user: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    pedido = session.get(PedidoAcessoSuporte, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if pedido.status != "aguardando_aprovacao":
        raise HTTPException(status_code=400, detail="Este pedido já foi decidido")
    pedido.status = "negado"
    pedido.aprovado_por_usuario_id = user.id
    pedido.decidido_em = datetime.utcnow()
    session.add(pedido)
    session.commit()
    session.refresh(pedido)
    return _publico_pedido(session, pedido)


@router.post("/sessoes/{sessao_id}/encerrar")
def encerrar_sessao(sessao_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    sessao = session.get(SessaoAcessoSuporte, sessao_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.encerrada_em is None:
        sessao.encerrada_em = datetime.utcnow()
        session.add(sessao)
        session.add(AuditoriaAcessoSuporte(fazenda_id=sessao.fazenda_id, usuario_id=sessao.usuario_id, acao="saida"))
        session.commit()
        session.refresh(sessao)
    return _publico_sessao(session, sessao)


@router.get("/sessoes-ativas")
def listar_sessoes_ativas(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    agora = datetime.utcnow()
    sessoes = session.exec(
        select(SessaoAcessoSuporte)
        .where(SessaoAcessoSuporte.encerrada_em == None, SessaoAcessoSuporte.expira_em > agora)  # noqa: E711
        .order_by(SessaoAcessoSuporte.iniciada_em.desc())
    ).all()
    return [_publico_sessao(session, s) for s in sessoes]


@router.get("/pedidos")
def listar_pedidos_recentes(
    limite: int = 20, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> list[dict]:
    pedidos = session.exec(
        select(PedidoAcessoSuporte).order_by(PedidoAcessoSuporte.pedido_em.desc()).limit(limite)
    ).all()
    return [_publico_pedido(session, p) for p in pedidos]


@router.get("/auditoria")
def listar_auditoria_recente(
    limite: int = 20, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> list[dict]:
    entradas = session.exec(
        select(AuditoriaAcessoSuporte).order_by(AuditoriaAcessoSuporte.quando.desc()).limit(limite)
    ).all()
    return [
        {
            "id": a.id, "quando": a.quando.isoformat(), "fazenda_id": a.fazenda_id,
            "fazenda_nome": _nome_fazenda(session, a.fazenda_id), "usuario_id": a.usuario_id,
            "membro_nome": _nome_usuario(session, a.usuario_id), "acao": a.acao,
        }
        for a in entradas
    ]
