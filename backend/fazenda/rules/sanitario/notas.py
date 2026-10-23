"""
Notas do sanitário na Agenda — escrita idempotente por `chave_dedupe`
(UNIQUE por fazenda). Nunca duplica: a mesma chave atualiza o texto da nota
aberta; nota resolvida não reabre sozinha (a menos que `reabrir=True`).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Session, select


def upsert_nota(
    session: Session, fazenda_id: int, chave: str, *, tipo: str, titulo: str, texto: Optional[str] = None,
    dados: Optional[dict] = None, caixa_id: Optional[int] = None, ciclo_chave: Optional[str] = None,
    dia_id: Optional[int] = None, so_admin: bool = True, data_ref: Optional[date] = None, reabrir: bool = False,
) -> tuple:
    """Devolve (nota, criada?)."""
    from fazenda.models import SanitarioNotaAgenda

    nota = session.exec(select(SanitarioNotaAgenda).where(
        SanitarioNotaAgenda.fazenda_id == fazenda_id, SanitarioNotaAgenda.chave_dedupe == chave,
    )).first()
    agora = datetime.utcnow()
    if nota is None:
        nota = SanitarioNotaAgenda(
            fazenda_id=fazenda_id, tipo=tipo, chave_dedupe=chave, titulo=titulo, texto=texto, dados=dados,
            caixa_id=caixa_id, ciclo_chave=ciclo_chave, dia_id=dia_id, so_admin=so_admin, data_ref=data_ref,
            criado_em=agora, atualizado_em=agora,
        )
        session.add(nota)
        session.flush()
        return nota, True
    if nota.resolvida_em is not None and not reabrir:
        return nota, False
    mudou = (nota.titulo, nota.texto, nota.dados, nota.data_ref) != (titulo, texto, dados, data_ref)
    if mudou or nota.resolvida_em is not None:
        nota.titulo, nota.texto, nota.dados, nota.data_ref = titulo, texto, dados, data_ref
        nota.resolvida_em = None
        nota.atualizado_em = agora
        session.add(nota)
    return nota, False


def resolver_notas(session: Session, fazenda_id: int, *, prefixo: Optional[str] = None,
                   chave: Optional[str] = None) -> int:
    """Marca como resolvidas as notas abertas com a chave (ou o prefixo)."""
    from fazenda.models import SanitarioNotaAgenda

    q = select(SanitarioNotaAgenda).where(
        SanitarioNotaAgenda.fazenda_id == fazenda_id, SanitarioNotaAgenda.resolvida_em == None,  # noqa: E711
    )
    if chave is not None:
        q = q.where(SanitarioNotaAgenda.chave_dedupe == chave)
    elif prefixo is not None:
        q = q.where(SanitarioNotaAgenda.chave_dedupe.startswith(prefixo))
    n = 0
    for nota in session.exec(q).all():
        nota.resolvida_em = datetime.utcnow()
        session.add(nota)
        n += 1
    return n
