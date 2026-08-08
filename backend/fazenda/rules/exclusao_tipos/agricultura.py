"""
Tipos de exclusão do domínio de Agricultura — preenchido pelo Agente D
(Cadastro, Protocolos, Agricultura, Configurações): G11 (`safra`).
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import select

from fazenda.models import Safra
from fazenda.rules.exclusao_tipos._base import TipoExclusao, _br, _contem, _dentro_periodo


def _buscar_safras(termo: str, data_inicio: str, data_fim: str, session, fazenda_id: int | None) -> list[dict]:
    query = select(Safra)
    if fazenda_id is not None:
        query = query.where(Safra.fazenda_id == fazenda_id)
    saidas = []
    # Ativas e inativas: uma safra com `ativo=False` (soft-delete de hoje) já
    # "sumiu" da UI normal, mas continua elegível para exclusão de verdade
    # aqui — não filtrar por `ativo`.
    for s in session.exec(query).all():
        if not _contem(termo, s.nome, s.centro_custo, s.observacao):
            continue
        if not _dentro_periodo(s.data_inicio, data_inicio, data_fim):
            continue
        saidas.append({
            "id": str(s.id),
            "titulo": f"{s.nome} — {_br(s.data_inicio)} a {_br(s.data_fim)}",
            "subtitulo": f"{s.hectares:g} ha · {s.toneladas_produzidas:g} t · {s.centro_custo}",
            "_data": s.data_inicio,
        })
    return saidas[:200]


def _alvos_safra(id_: str, session, fazenda_id: int | None) -> tuple[list[str], list]:
    safra = session.get(Safra, int(id_))
    if not safra or (fazenda_id is not None and safra.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Safra não encontrada")
    impacto = [
        f"Safra {safra.nome}",
        "O relatório de custo por hectare/tonelada desta safra deixa de existir "
        "(os lançamentos financeiros do centro de custo NÃO são apagados)",
    ]
    # Sem efeitos colaterais: Safra não tem nenhuma FK apontando para ela.
    return impacto, [safra]


TIPOS_EXCLUSAO: list[TipoExclusao] = [
    TipoExclusao(
        id="safra",
        label="Safra (Agricultura)",
        buscar=_buscar_safras,
        alvos=_alvos_safra,
        sem_filtro_data=False,
    ),
]
