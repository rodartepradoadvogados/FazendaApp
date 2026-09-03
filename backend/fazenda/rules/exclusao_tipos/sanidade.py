"""
Tipos de exclusão do domínio de Sanidade — `exame_resultado` (diagnóstico de
exame preventivo lançado via calendário sanitário, ver
api/routers/sanidade.py::cadastrar_preventivo). Antes desta rota, o relatório
de exames era só leitura e não havia como apagar um lançamento errado.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from fazenda.models import Animal, EventoSanitario, ExameResultado
from fazenda.rules.exclusao_tipos._base import TipoExclusao, _br, _contem, _dentro_periodo


def _buscar_exame_resultado(
    termo: str = "", data_inicio: str = "", data_fim: str = "",
    session: Session | None = None, fazenda_id: int | None = None, **_,
) -> list[dict]:
    query = select(ExameResultado)
    if fazenda_id is not None:
        query = query.where(ExameResultado.fazenda_id == fazenda_id)
    eventos = {e.id: e.nome for e in session.exec(select(EventoSanitario)).all()}
    out = []
    for r in session.exec(query).all():
        nome_evento = eventos.get(r.evento_sanitario_id, "") or ""
        if not _contem(termo, r.numero_matriz, nome_evento, r.resultado, r.veterinario):
            continue
        if not _dentro_periodo(r.data_exame, data_inicio, data_fim):
            continue
        subtitulo = r.resultado or (f"{r.valor_numerico:g}" if r.valor_numerico is not None else "—")
        out.append({
            "id": r.id,
            "titulo": f"{nome_evento or 'Exame'} — {r.numero_matriz} — {_br(r.data_exame)}",
            "subtitulo": subtitulo,
            "_data": r.data_exame,
        })
    return sorted(out, key=lambda x: x["_data"], reverse=True)[:200]


def _alvos_exame_resultado(id_: str, session: Session | None = None, fazenda_id: int | None = None, **_) -> tuple[list[str], list]:
    r = session.get(ExameResultado, int(id_))
    if not r or (fazenda_id is not None and r.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Resultado de exame não encontrado")
    ev = session.get(EventoSanitario, r.evento_sanitario_id)
    impacto = [f'Resultado de "{ev.nome if ev else "exame"}" de {r.numero_matriz} em {_br(r.data_exame)}']

    # positivo marcou "A descartar" automaticamente ao ser lançado (ver
    # cadastrar_preventivo) — reverte aqui, dentro de `alvos`, igual à
    # reversão de saldo em estoque.py::_alvos_movimento_estoque: o efeito
    # colateral automático não pode sobreviver à exclusão do exame que o
    # causou.
    if r.resultado == "positivo":
        query_animal = select(Animal).where(Animal.numero == r.numero_matriz)
        if fazenda_id is not None:
            query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
        animal = session.exec(query_animal).first()
        if animal and animal.a_descartar:
            animal.a_descartar = False
            animal.a_descartar_em = None
            animal.descarte_previsto_em = None
            animal.atualizado_em = datetime.utcnow()
            session.add(animal)
            impacto.append(f'A marcação "A descartar" de {r.numero_matriz} (causada por este exame) será desfeita')

    return impacto, [r]


TIPOS_EXCLUSAO: list[TipoExclusao] = [
    TipoExclusao(
        id="exame_resultado",
        label="Resultado de exame preventivo",
        buscar=_buscar_exame_resultado,
        alvos=_alvos_exame_resultado,
    ),
]
