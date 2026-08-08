"""
Tipos de exclusão do domínio de Produção — preenchido pelo Agente C2
(Produção): G6 (`entrega_leite`), G7 (`pesagem_corporal`). G13 é só UI
(reusa o tipo `controle`, já existente no motor) — não mexe neste arquivo.
"""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlmodel import Session, select

from fazenda.models import EntregaLeiteMensal, PesagemCorporal
from fazenda.rules.exclusao_tipos._base import TipoExclusao, _br, _contem, _dentro_periodo


def _data_competencia(competencia: str | None) -> date | None:
    """"YYYY-MM" -> primeiro dia do mês, para servir de `_data` na ordenação
    e no filtro de período — competência mal formada não quebra a busca."""
    if not competencia:
        return None
    try:
        ano, mes = competencia.split("-")
        return date(int(ano), int(mes), 1)
    except (ValueError, AttributeError):
        return None


def _buscar_entrega_leite(
    termo: str = "", data_inicio: str = "", data_fim: str = "",
    session: Session | None = None, fazenda_id: int | None = None,
) -> list[dict]:
    query = select(EntregaLeiteMensal)
    if fazenda_id is not None:
        query = query.where(EntregaLeiteMensal.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    out = []
    for r in rows:
        if not _contem(termo, r.competencia, r.observacao):
            continue
        data_ref = _data_competencia(r.competencia)
        if not _dentro_periodo(data_ref, data_inicio, data_fim):
            continue
        out.append({
            "id": r.id,
            "titulo": f"Entrega de leite {r.competencia}",
            "subtitulo": f"{r.quantidade_litros:g} L",
            "_data": data_ref,
        })
    return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]


def _alvos_entrega_leite(id_: str, session: Session | None = None, fazenda_id: int | None = None) -> tuple[list[str], list]:
    r = session.get(EntregaLeiteMensal, int(id_))
    if not r or (fazenda_id is not None and r.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Entrega de leite não encontrada")
    return [f"Entrega de leite de {r.quantidade_litros:g} L na competência {r.competencia}"], [r]


def _buscar_pesagem_corporal(
    termo: str = "", data_inicio: str = "", data_fim: str = "",
    session: Session | None = None, fazenda_id: int | None = None,
) -> list[dict]:
    query = select(PesagemCorporal)
    if fazenda_id is not None:
        query = query.where(PesagemCorporal.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    out = []
    for p in rows:
        if not _contem(termo, p.numero_matriz, p.grupo_primario):
            continue
        if not _dentro_periodo(p.data_pesagem, data_inicio, data_fim):
            continue
        subtitulo = f"{p.peso_kg:g} kg" + (f" · {p.fase}" if p.fase else "")
        out.append({
            "id": p.id,
            "titulo": f"{p.numero_matriz} — {_br(p.data_pesagem)}",
            "subtitulo": subtitulo,
            "_data": p.data_pesagem,
        })
    return sorted(out, key=lambda x: x["titulo"], reverse=True)[:200]


def _alvos_pesagem_corporal(id_: str, session: Session | None = None, fazenda_id: int | None = None) -> tuple[list[str], list]:
    p = session.get(PesagemCorporal, int(id_))
    if not p or (fazenda_id is not None and p.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Pesagem não encontrada")
    return [
        f"Pesagem de {p.numero_matriz} em {_br(p.data_pesagem)} ({p.peso_kg:g} kg)",
        "O GMD/GPD do animal será recalculado",
    ], [p]


TIPOS_EXCLUSAO: list[TipoExclusao] = [
    TipoExclusao(
        id="entrega_leite",
        label="Entrega de leite (mensal)",
        buscar=_buscar_entrega_leite,
        alvos=_alvos_entrega_leite,
    ),
    TipoExclusao(
        id="pesagem_corporal",
        label="Pesagem corporal",
        buscar=_buscar_pesagem_corporal,
        alvos=_alvos_pesagem_corporal,
    ),
]
