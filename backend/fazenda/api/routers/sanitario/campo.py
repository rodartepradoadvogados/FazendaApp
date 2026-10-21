"""
/sanitario — app de campo: dias de hoje/amanhã, pacote offline do dia (as
regras de aviso como DADOS), sincronização em lote idempotente (resposta por
registro; conflito entre aparelhos vira decisão do aplicador/admin) e o
heartbeat do aparelho (contagem de pendentes; o job avisa o administrador
quando passa de N horas sem enviar).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.api.routers.sanitario._comum import da_fazenda, exigir_admin_fazenda, exigir_fazenda, traduzir_erros
from fazenda.api.routers.sanitario.dias import dispositivo_por_uid
from fazenda.api.routers.sanitario.schemas import HeartbeatIn, SincronizarIn
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import SanitarioDia, SanitarioDispositivo, Usuario
from fazenda.rules.datas import hoje_local
from fazenda.rules.sanitario import dias as regras_dias
from fazenda.rules.sanitario import registro as regras_reg
from fazenda.rules.sanitario.permissoes import eh_admin_fazenda

router = APIRouter(tags=["sanitario-campo"])


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


@router.get("/campo/hoje")
def campo_hoje(session: Session = Depends(get_session),
               fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    """Dias abertos de hoje e de amanhã (menu Vacinação / véspera)."""
    fid = exigir_fazenda(fazenda_id)
    hoje = hoje_local()
    dias = session.exec(select(SanitarioDia).where(
        SanitarioDia.fazenda_id == fid, SanitarioDia.estado.in_(regras_dias.ESTADOS_ABERTOS),
        SanitarioDia.data <= hoje + timedelta(days=1)).order_by(SanitarioDia.data, SanitarioDia.id)).all()
    return {"hoje": hoje.isoformat(), "dias": [{**regras_dias.dia_dict(session, d, com_itens=False),
                                                "quando": "hoje" if d.data <= hoje else "amanha"} for d in dias]}


@router.get("/dias/{dia_id}/pacote-offline")
def pacote_offline(dia_id: int, session: Session = Depends(get_session),
                   fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    dia = da_fazenda(session, SanitarioDia, dia_id, fid, "Dia")
    return regras_dias.pacote_offline(session, fid, dia)


def _heartbeat(session: Session, disp: SanitarioDispositivo, pendentes: int, mais_antigo: Optional[datetime]) -> None:
    disp.ultimo_contato_em = datetime.utcnow()
    disp.fila_pendentes = int(pendentes or 0)
    disp.fila_mais_antigo_em = _utc(mais_antigo) if pendentes else None
    if not pendentes:
        disp.aviso_admin_em = None
    session.add(disp)


@router.post("/dispositivos/heartbeat")
def heartbeat(dados: HeartbeatIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
              fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Em todo contato o app informa quantos registros guarda. Se o último
    informe tinha registros e o aparelho some por 24 h, o job manda push ao
    administrador."""
    fid = exigir_fazenda(fazenda_id)
    disp = dispositivo_por_uid(session, fid, user.id, dados.dispositivo_uid, dados.nome)
    _heartbeat(session, disp, dados.fila_pendentes, dados.fila_mais_antigo_em)
    if not dados.fila_pendentes:
        from fazenda.rules.sanitario.notas import resolver_notas
        resolver_notas(session, fid, prefixo=f"offline:{disp.id}:")
    session.commit()
    session.refresh(disp)
    return _disp_dict(disp)


def _disp_dict(d: SanitarioDispositivo) -> dict:
    return {"id": d.id, "dispositivo_uid": d.dispositivo_uid, "nome": d.nome, "usuario_id": d.usuario_id,
            "ultimo_contato_em": d.ultimo_contato_em.isoformat() + "Z" if d.ultimo_contato_em else None,
            "fila_pendentes": d.fila_pendentes,
            "fila_mais_antigo_em": d.fila_mais_antigo_em.isoformat() + "Z" if d.fila_mais_antigo_em else None,
            "aviso_admin_em": d.aviso_admin_em.isoformat() + "Z" if d.aviso_admin_em else None}


@router.get("/dispositivos")
def listar_dispositivos(session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
                        fazenda_id: Optional[int] = Depends(get_fazenda_atual_id)) -> list[dict]:
    fid = exigir_fazenda(fazenda_id)
    exigir_admin_fazenda(session, user, fid)
    return [_disp_dict(d) for d in session.exec(select(SanitarioDispositivo).where(
        SanitarioDispositivo.fazenda_id == fid).order_by(SanitarioDispositivo.id)).all()]


@router.post("/campo/sincronizar")
def sincronizar(dados: SincronizarIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
                fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    """Envio em lote da fila do celular. Idempotente por `chave_idempotencia`
    (reenviar não duplica); resposta POR REGISTRO (gravado | duplicado |
    conflito | pendente | erro). Dia já fechado: entra como "lançado após o
    fechamento". Um conflito entre dois aparelhos fica para o aplicador ou o
    administrador decidir (POST /sanitario/conflitos/{id}/decidir)."""
    fid = exigir_fazenda(fazenda_id)
    adm = eh_admin_fazenda(session, user, fid)
    disp = dispositivo_por_uid(session, fid, user.id, dados.dispositivo_uid, dados.nome)
    por_dia: dict[Optional[int], list[tuple[int, dict]]] = {}
    for i, r in enumerate(dados.registros):
        d = r.model_dump()
        por_dia.setdefault(d.pop("dia_id"), []).append((i, d))
    resultados: list[Optional[dict]] = [None] * len(dados.registros)
    with traduzir_erros(session):
        for dia_id, itens in por_dia.items():
            dia = None
            if dia_id is not None:
                dia = session.get(SanitarioDia, dia_id)
                if dia is None or dia.fazenda_id != fid or dia.estado == "cancelado":
                    for i, it in itens:
                        resultados[i] = {"indice": i, "status": "erro", "registro_id": None,
                                         "chave_idempotencia": it.get("chave_idempotencia"),
                                         "avisos": [{"codigo": "dia_inexistente", "texto": "Dia não encontrado ou cancelado."}],
                                         "requer": []}
                    continue
            res = regras_reg.registrar(
                session, fid, [it for _i, it in itens], origem="dia" if dia is not None else "lancamento_simples",
                canal="app", usuario_id=user.id, eh_admin=adm, dia=dia, dispositivo_id=disp.id,
            )
            for (i, _it), r in zip(itens, res["itens"]):
                r["indice"] = i
                resultados[i] = r
        _heartbeat(session, disp, dados.fila_pendentes_restantes, None)
        session.commit()
    cont = {k: sum(1 for x in resultados if x and x["status"] == v) for k, v in (
        ("gravados", "gravado"), ("duplicados", "duplicado"), ("pendentes", "pendente"),
        ("conflitos", "conflito"), ("erros", "erro"))}
    return {"dispositivo_id": disp.id, **cont, "itens": resultados}
