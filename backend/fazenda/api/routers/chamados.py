"""
Router de Chamados — suporte aberto pelo contador (ou pela fazenda) para o
administrador/CowData. Registrado em main.py COM bloquear_escrita_contador
(mesmo padrão de financeiro/planejamento): o contador só cria um chamado com
o cadeado destravado (ver fazenda/auth.py::bloquear_escrita_contador e
POST /auth/desbloquear).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Chamado, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/chamados", tags=["chamados"])


class ChamadoIn(BaseModel):
    assunto: str
    descricao: str


class ChamadoStatusIn(BaseModel):
    status: str
    resposta: str | None = None


def _serializar(c: Chamado) -> dict:
    return {
        "id": c.id, "assunto": c.assunto, "descricao": c.descricao, "status": c.status,
        "criado_em": c.criado_em.isoformat(), "atualizado_em": c.atualizado_em.isoformat(),
        "resposta": c.resposta,
    }


@router.get("")
def listar_chamados(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Chamado)
    if fazenda_id is not None:
        query = query.where(Chamado.fazenda_id == fazenda_id)
    chamados = session.exec(query.order_by(Chamado.criado_em.desc())).all()
    return [_serializar(c) for c in chamados]


@router.post("", status_code=201)
def abrir_chamado(
    dados: ChamadoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    chamado = Chamado(
        fazenda_id=fazenda_id, usuario_id=user.id if isinstance(user, Usuario) else None,
        assunto=dados.assunto, descricao=dados.descricao,
    )
    session.add(chamado)
    session.commit()
    session.refresh(chamado)
    return _serializar(chamado)


@router.put("/{chamado_id}")
def atualizar_status_chamado(
    chamado_id: int, dados: ChamadoStatusIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    _admin: Usuario = Depends(exigir_admin),
) -> dict:
    # BUG DE SEGURANÇA CORRIGIDO: qualquer usuário autenticado (inclusive
    # "operador") podia mudar status/resposta de um chamado — agora exige
    # admin, mesmo padrão de exclusão de documento em documentos.py.
    if dados.status not in ("aberto", "em_andamento", "resolvido"):
        raise HTTPException(status_code=400, detail="status deve ser 'aberto', 'em_andamento' ou 'resolvido'")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    chamado = session.get(Chamado, chamado_id)
    if not chamado or (fazenda_id is not None and chamado.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Chamado não encontrado")
    chamado.status = dados.status
    if dados.resposta is not None:
        chamado.resposta = dados.resposta
    chamado.atualizado_em = datetime.utcnow()
    session.add(chamado)
    session.commit()
    session.refresh(chamado)
    return _serializar(chamado)
