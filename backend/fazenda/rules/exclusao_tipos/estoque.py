"""
Tipos de exclusão do domínio de Estoque — preenchido pelo Agente A (Estoque &
Financeiro): G1 (`movimento_estoque`, exclusão de movimento manual).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlmodel import select

from fazenda.api.routers.estoque import MOVIMENTOS_SAIDA
from fazenda.models import Estoque, EstoqueSemen, MovimentoEstoque
from fazenda.rules.exclusao_tipos._base import TipoExclusao, _br, _contem, _dentro_periodo


def _resolver_item(mov: MovimentoEstoque, session, fazenda_id: int | None) -> Estoque | None:
    """Espelha `_resolver_item_do_movimento` de `api/routers/estoque.py` —
    `estoque_id` pode ser `None` em movimentos legados, resolve por
    `nome_item` + `fazenda_id` nesse caso."""
    if mov.estoque_id:
        item = session.get(Estoque, mov.estoque_id)
        if item:
            return item
    query = select(Estoque).where(Estoque.nome == mov.nome_item)
    if fazenda_id is not None:
        query = query.where(Estoque.fazenda_id == fazenda_id)
    return session.exec(query).first()


def _buscar_movimento_estoque(
    termo: str, data_inicio: str, data_fim: str, session, fazenda_id: int | None = None, **_,
) -> list[dict]:
    """Só movimentos manuais (`origem_tipo is None`) — os gerados por outro
    lançamento (Sanidade, Protocolo, Secagem…) são excluídos por lá, ver a
    guarda em `alvos`."""
    query = select(MovimentoEstoque).where(MovimentoEstoque.origem_tipo.is_(None))
    if fazenda_id is not None:
        query = query.where(MovimentoEstoque.fazenda_id == fazenda_id)
    rows = session.exec(query).all()
    out = [
        {
            "id": m.id,
            "titulo": f"{m.nome_item} — {m.movimento} — {_br(m.data_movimento)}",
            "subtitulo": f"{m.quantidade:g} {m.unidade or ''}",
            "_data": m.data_movimento,
        }
        for m in rows
        if _contem(termo, m.nome_item, m.movimento, m.observacao)
        and _dentro_periodo(m.data_movimento, data_inicio, data_fim)
    ]
    return sorted(out, key=lambda x: x["_data"], reverse=True)[:200]


def _alvos_movimento_estoque(id_: str, session, fazenda_id: int | None = None, **_) -> tuple[list[str], list]:
    mov = session.get(MovimentoEstoque, int(id_))
    if not mov or (fazenda_id is not None and mov.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Movimento de estoque não encontrado")
    if mov.origem_tipo is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Este movimento foi gerado por um lançamento de {mov.origem_tipo} — desfaça pelo próprio "
            "lançamento (Sanidade, Protocolo, Secagem…), não pelo histórico de estoque.",
        )
    if mov.pedido_item_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Esta entrada está vinculada a um item de pedido — desfaça pelo Pedido.",
        )

    impacto = [
        f'Movimento "{mov.movimento}" de {mov.quantidade:g} {mov.unidade or ""} de {mov.nome_item} em {_br(mov.data_movimento)}'
    ]

    # A reversão de saldo acontece AQUI, dentro de `alvos` — não numa rota
    # separada — porque `get_session` não commita no teardown e só
    # `confirmar`/`aprovar_pendente` commitam (ver `_base.py`/`exclusoes.py`).
    item = _resolver_item(mov, session, fazenda_id)
    if item is not None:
        sinal = -1 if mov.movimento in MOVIMENTOS_SAIDA else 1
        saldo_atual = item.quantidade or 0
        saldo_revertido = saldo_atual - sinal * mov.quantidade
        impacto.append(f"Saldo de {mov.nome_item} volta de {saldo_atual:g} para {saldo_revertido:g}")
        if saldo_revertido < 0:
            impacto.append(f"Atenção: o saldo de {mov.nome_item} fica negativo ({saldo_revertido:g}) após a reversão")

        item.quantidade = saldo_revertido
        if item.estoque_minimo is not None:
            item.abaixo_minimo = item.quantidade < item.estoque_minimo
        item.atualizado_em = datetime.utcnow()
        session.add(item)

        if item.estoque_semen_id:
            touro = session.get(EstoqueSemen, item.estoque_semen_id)
            if touro:
                touro.doses = touro.doses - round(sinal * mov.quantidade)
                touro.atualizado_em = datetime.utcnow()
                session.add(touro)

    return impacto, [mov]


TIPOS_EXCLUSAO: list[TipoExclusao] = [
    TipoExclusao(
        id="movimento_estoque",
        label="Movimento de estoque (entrada/saída manual)",
        buscar=_buscar_movimento_estoque,
        alvos=_alvos_movimento_estoque,
        sem_filtro_data=False,
    ),
]
