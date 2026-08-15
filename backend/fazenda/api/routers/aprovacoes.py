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

from fazenda.auth import exigir_admin, exigir_pode_publicar, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
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
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Aprova e MATERIALIZA o lançamento — cria o registro real. Se a criação
    falhar (ex.: animal inexistente), guarda o erro e mantém como pendente.

    `criar_registro` grava fazenda_id no(s) registro(s) reais criados — antes
    disso, o lançamento aprovado pelo Telegram sempre nascia com fazenda_id
    NULO (nenhum `user`/`fazenda_id` chegava até lá, só `dados` e `session`;
    ver fazenda_id_seguro/usuario_id_seguro em rules/auditoria.py). Prioriza
    `p.fazenda_id` quando o próprio bot já sabia de qual fazenda é o chat
    (TELEGRAM_CHAT_FAZENDA, ver `_fazenda_do_chat` em telegram.py); sem isso,
    cai para a fazenda da sessão de quem está aprovando — `fazenda_id` aqui
    NUNCA é None (get_fazenda_id_escrita recusa a aprovação com 409 antes
    de chegar aqui se não der pra resolver com segurança)."""
    p = session.get(LancamentoPendente, pendente_id)
    if not p:
        raise HTTPException(status_code=404, detail="Lançamento pendente não encontrado")
    _verificar_posse(p, fazenda_id)
    _exigir_permissao_do_tipo(p, user)
    if p.status != "pendente":
        raise HTTPException(status_code=409, detail=f"Este lançamento já está {p.status}.")

    fazenda_id_materializacao = p.fazenda_id if p.fazenda_id is not None else fazenda_id
    try:
        resultado = fx.criar_registro(
            p.tipo, json.loads(p.payload or "{}"), session, user=user, fazenda_id=fazenda_id_materializacao,
        )
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

    # G17 — grava o que foi materializado de fato, para permitir desfazer
    # depois (ver `POST /{pendente_id}/desfazer`). `criar_registro` sempre
    # devolve uma chave "registros" em `resultado` desde o G17 (lista de
    # {"tipo","id"} ou {"reversivel": false, "motivo": ...}); o fallback
    # genérico abaixo só cobre um ramo que porventura esqueça de defini-la.
    registros = resultado.get("registros") if isinstance(resultado, dict) else None
    if not registros:
        registros = {
            "reversivel": False,
            "motivo": "Este tipo de lançamento não tem desfazer automático implementado.",
        }
    p.registro_criado = json.dumps(registros)

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


# ─────────────────────── G17 — Desfazer aprovação/rejeição ──────────────────
#
# Fila de DECIDIDOS (aprovados/rejeitados), com a possibilidade de desfazer:
# rejeitado volta a pendente sem mais nada; aprovado volta a pendente E
# desfaz o que foi materializado, reusando o mesmo trio do motor genérico de
# exclusões (`exclusoes.confirmar`) — desvincula vale, estorna estoque,
# `session.delete`. Import LOCAL de `fazenda.api.routers.exclusoes` (nunca no
# topo do módulo) para não criar o ciclo `exclusoes -> aprovacoes ->
# exclusoes` (aprovacoes já é importado por telegram_fluxos/rotas diversas).

def _pode_desfazer(session: Session, p: LancamentoPendente, fazenda_id: int | None) -> tuple[bool, str | None]:
    if p.status == "rejeitado":
        return True, None
    if p.status != "aprovado":
        return False, None
    if not p.registro_criado:
        return False, (
            "Este lançamento foi aprovado antes do recurso de desfazer existir "
            "— não há registro do que foi criado para reverter."
        )
    try:
        registros = json.loads(p.registro_criado)
    except (TypeError, ValueError):
        return False, "Não foi possível interpretar o que este lançamento criou."
    if not isinstance(registros, list) or not registros:
        motivo = registros.get("motivo") if isinstance(registros, dict) else None
        return False, motivo or "Este tipo de lançamento não tem desfazer automático."

    from fazenda.api.routers.exclusoes import _alvos

    for reg in registros:
        try:
            _alvos(reg.get("tipo"), str(reg.get("id")), session, fazenda_id=fazenda_id)
        except HTTPException:
            return False, "Um ou mais registros criados por este lançamento já não existem mais (foram excluídos por outro caminho)."
    return True, None


@router.get("/decididas", dependencies=[Depends(exigir_admin)])
def listar_decididas(
    limite: int = 30, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Lançamentos já decididos (aprovado/rejeitado), do mais recente para o
    mais antigo, com `pode_desfazer` calculado na hora (não é armazenado —
    `_alvos` faz um efeito colateral SE existir algum, mas a sessão desta
    rota GET nunca commita, então nada persiste, ver `get_session`)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(LancamentoPendente).where(LancamentoPendente.status.in_(("aprovado", "rejeitado")))
    if fazenda_id is not None:
        query = query.where(LancamentoPendente.fazenda_id.in_((fazenda_id, None)))
    pend = session.exec(query.order_by(LancamentoPendente.decidido_em.desc()).limit(limite)).all()
    saida = []
    for p in pend:
        pode, motivo = _pode_desfazer(session, p, fazenda_id)
        saida.append({**_dto(p), "pode_desfazer": pode, "motivo_nao_desfaz": motivo})
    return saida


@router.post("/{pendente_id}/desfazer")
def desfazer(
    pendente_id: int, session: Session = Depends(get_session), user: Usuario = Depends(exigir_admin),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Rejeitado → volta a pendente (pode ser reavaliado). Aprovado → desfaz o
    que foi criado (reversão de estado incluída — desvincula vale, estorna
    estoque) e também volta a pendente. 409 se ainda estiver pendente (nada
    para desfazer)."""
    p = session.get(LancamentoPendente, pendente_id)
    if not p:
        raise HTTPException(status_code=404, detail="Lançamento pendente não encontrado")
    _verificar_posse(p, fazenda_id)
    _exigir_permissao_do_tipo(p, user)
    fazenda_id_ok = fazenda_id_seguro(fazenda_id)

    if p.status == "pendente":
        raise HTTPException(status_code=409, detail="Este lançamento ainda está pendente — não há decisão para desfazer.")

    if p.status == "rejeitado":
        p.status = "pendente"
        p.decidido_em = None
        p.decidido_por = None
        p.erro = None
        session.add(p)
        session.commit()
        return {"desfeito": True, "status": p.status}

    # status == "aprovado"
    if not p.registro_criado:
        raise HTTPException(
            status_code=400,
            detail="Este lançamento foi aprovado antes do recurso de desfazer existir — não há como reverter automaticamente.",
        )
    try:
        registros = json.loads(p.registro_criado)
    except (TypeError, ValueError):
        registros = None
    if not isinstance(registros, list) or not registros:
        motivo = registros.get("motivo") if isinstance(registros, dict) else None
        raise HTTPException(status_code=400, detail=motivo or "Este tipo de lançamento não tem desfazer automático.")

    from fazenda.api.routers.exclusoes import _alvos, _desvincular_vales_dos_alvos, _estornar_estoque_dos_alvos

    avisos: list[str] = []
    for reg in registros:
        tipo, id_ = reg.get("tipo"), reg.get("id")
        try:
            _, alvos = _alvos(tipo, str(id_), session, fazenda_id=fazenda_id_ok)
        except HTTPException as e:
            avisos.append(f"{tipo} #{id_}: {e.detail} — ignorado, o resto do desfazer continuou.")
            continue
        _desvincular_vales_dos_alvos(session, alvos, fazenda_id_ok)
        avisos.extend(_estornar_estoque_dos_alvos(session, alvos, fazenda_id_ok, tipo))
        for obj in alvos:
            session.delete(obj)

    p.status = "pendente"
    p.decidido_em = None
    p.decidido_por = None
    p.registro_criado = None
    p.erro = None
    session.add(p)
    session.commit()
    return {"desfeito": True, "status": p.status, "avisos": avisos}
