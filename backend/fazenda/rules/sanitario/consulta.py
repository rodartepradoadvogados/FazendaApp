"""
Leituras agregadas do sanitário — SÓ LEITURA (nenhuma chama add/commit).
Contagens são sempre de animais DISTINTOS; nunca se soma entre caixas.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from fazenda.rules.datas import hoje_local
from fazenda.rules.sanitario.tipos import ESTADOS_NA_CAIXA


def _quando(row, hoje: date) -> Optional[date]:
    if row.estado == "marcada":
        return None  # o dia conta à parte
    if row.estado in ("janela", "atrasada"):
        return hoje
    if row.estado in ("aviso", "prevista"):
        return row.data_base or row.janela_inicio
    return None


def resumo_30d(session: Session, fazenda_id: int, hoje: Optional[date] = None, dias: int = 30) -> dict:
    """Card "Vacinas previstas" da Agenda: só números (animais distintos,
    caixas e dias marcados nos próximos `dias`)."""
    from fazenda.models import SanitarioCaixa, SanitarioDia, SanitarioSituacao

    hoje = hoje or hoje_local()
    ate = hoje + timedelta(days=dias)
    ativas = set(session.exec(select(SanitarioCaixa.id).where(
        SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.estado == "ativa")).all())
    animais, caixas = set(), set()
    for r in session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fazenda_id,
        SanitarioSituacao.estado.in_(("janela", "atrasada", "aviso", "prevista", "marcada")),
    )).all():
        if r.caixa_id not in ativas:
            continue
        q = _quando(r, hoje)
        if r.estado == "marcada" or (q is not None and q <= ate):
            animais.add(r.animal_id)
            caixas.add(r.caixa_id)
    n_dias = len(session.exec(select(SanitarioDia.id).where(
        SanitarioDia.fazenda_id == fazenda_id, SanitarioDia.estado.in_(("marcado", "em_execucao")),
        SanitarioDia.data >= hoje, SanitarioDia.data <= ate,
    )).all())
    return {"animais": len(animais), "caixas": len(caixas), "dias": n_dias, "periodo_dias": dias}


def membros(session: Session, fazenda_id: int, caixa_id: int, estados=ESTADOS_NA_CAIXA) -> list:
    """Linhas de situação da caixa nos estados pedidos (padrão: na caixa)."""
    from fazenda.models import SanitarioSituacao

    return list(session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fazenda_id, SanitarioSituacao.caixa_id == caixa_id,
        SanitarioSituacao.estado.in_(tuple(estados)),
    ).order_by(SanitarioSituacao.animal_id)).all())


def situacao_do_animal(session: Session, fazenda_id: int, animal_id: int, hoje: Optional[date] = None) -> list:
    """Situação ao vivo (motor puro) do animal em todas as caixas ativas —
    não lê nem grava `sanitario_situacao`."""
    from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas
    from fazenda.rules.sanitario.motor import avaliar

    animais = carregar_animais(session, fazenda_id, animal_ids=[animal_id], hoje=hoje)
    a = animais.get(animal_id)
    if a is None:
        return []
    out = []
    for cx in carregar_caixas(session, fazenda_id, so_ativas=True):
        for s in avaliar(cx, a):
            out.append({
                "caixa_id": cx.caixa_id, "caixa": cx.rotulo, "estado": s.estado, "texto": s.texto,
                "ciclo": s.ciclo_chave, "dose": s.dose_num,
                "janela_inicio": s.ciclo.ini.isoformat() if s.ciclo and s.ciclo.chave != "C" else None,
                "janela_fim": s.ciclo.fim.isoformat() if s.ciclo and s.ciclo.chave != "C" else None,
                "motivos": [{"ok": m.ok, "texto": m.texto} for m in s.motivos],
            })
    return out
