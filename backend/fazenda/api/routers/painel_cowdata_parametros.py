"""
Painel CowData > Parâmetros — visão agregada e edição em massa dos
parâmetros gerais/financeiros de todas as fazendas-cliente de uma vez, ou só
das selecionadas, sem precisar entrar em cada uma via modo suporte. Mesmo
espírito de painel_cowdata_cadastros.py, mas em cima de `ParametroFazenda`
(chave + fazenda_id + valor — ver fazenda/models/sistema.py), que já tem uma
linha "padrão global" (fazenda_id NULL) usada por toda fazenda que não
personalizou (ver rules.parametros._linha e a correção de isolamento em
api/routers/parametros.py).

Escopo: só os 36 parâmetros de `ParametroFazenda` — "gerais" e "financeiro"
aqui são grupos DENTRO dessa mesma tabela (ver GRUPO_TITULOS), não a aba
"Parâmetros financeiros" da fazenda (contas correntes, plano de contas,
centro de custo — fazenda/api/routers/financeiro.py). Aquelas tabelas
guardam dado de identidade por fazenda (nº de conta bancária, por exemplo) —
nunca fazem sentido como "aplicar o mesmo valor em todas as fazendas de uma
vez" e ficam de fora por design.

"Aplicar em todas as fazendas ativas" (fazenda_ids vazio/None) TAMBÉM
atualiza a linha padrão global (fazenda_id NULL), para toda fazenda nova
criada dali em diante já nascer com o novo valor — é o único caso em que
essa seção mexe na linha global. Selecionar fazendas específicas nunca toca
a linha global, só cria/atualiza a linha daquelas fazendas (mesmo padrão de
Cadastros globais).

RLS (auditoria de 11/09/2026, ver docs/security-audit/roteiro-seguranca.md):
`listar_parametros`/`aplicar_parametro` usam `Depends(get_session_manutencao)`
— mesmo motivo de painel_cowdata_cadastros.py. `parametro_fazenda` é
catálogo global no DDL de RLS (leitura da linha `fazenda_id IS NULL`
funcionaria mesmo sem isto), mas a ESCRITA dessa mesma linha e toda leitura/
escrita das linhas por fazenda não têm essa exceção — sem a correção,
`aplicar_parametro` falharia com 500 na primeira fazenda do laço.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.painel_cowdata_cadastros import _fazendas_alvo, _fazendas_ativas
from fazenda.auth import exigir_area_painel_cowdata
from fazenda.database import get_session, get_session_manutencao
from fazenda.models import ParametroFazenda, Usuario
from fazenda.rules.parametros import GRUPO_TITULOS

router = APIRouter(prefix="/painel-cowdata/parametros", tags=["painel-cowdata-parametros"])


def _valor_convertido(linha: ParametroFazenda) -> float | int | bool | str | None:
    if linha.tipo == "bool":
        return (linha.valor or "").strip().lower() in ("1", "true", "sim", "yes")
    if linha.tipo == "date":
        return linha.valor
    if linha.tipo == "float":
        try:
            return float(linha.valor)
        except (TypeError, ValueError):
            return None
    try:
        return int(float(linha.valor))
    except (TypeError, ValueError):
        return None


@router.get("/fazendas")
def listar_fazendas_alvo(
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> list[dict]:
    return [{"id": f.id, "nome": f.nome} for f in _fazendas_ativas(session)]


@router.get("/")
def listar_parametros(
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")),
    session: Session = Depends(get_session_manutencao),
) -> dict:
    """Visão agregada: valor padrão global de cada chave + quais fazendas já
    personalizaram (para o usuário saber que "aplicar em todas" não vai
    mudar o que essas fazendas veem, a menos que sejam incluídas na seleção)."""
    todas = session.exec(select(ParametroFazenda).order_by(ParametroFazenda.id)).all()
    por_chave: dict[str, dict] = {}
    for linha in todas:
        item = por_chave.setdefault(linha.chave, {
            "chave": linha.chave, "label": linha.label, "grupo": linha.grupo, "tipo": linha.tipo,
            "unidade": linha.unidade, "valor_global": None, "personalizado_em": [],
        })
        if linha.fazenda_id is None:
            item["valor_global"] = _valor_convertido(linha)
        else:
            item["personalizado_em"].append(linha.fazenda_id)

    grupos: dict[str, dict] = {}
    for grupo_id, titulo in GRUPO_TITULOS.items():
        grupos[grupo_id] = {"titulo": titulo, "itens": []}
    for item in por_chave.values():
        grupo = grupos.setdefault(item["grupo"], {"titulo": item["grupo"], "itens": []})
        item["total_personalizados"] = len(item["personalizado_em"])
        grupo["itens"].append(item)
    grupos = {k: v for k, v in grupos.items() if v["itens"]}
    return {"grupos": grupos}


class AplicarParametroIn(BaseModel):
    valor: float | int | bool | str
    fazenda_ids: list[int] | None = None


@router.put("/{chave}")
def aplicar_parametro(
    chave: str, dados: AplicarParametroIn,
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")),
    session: Session = Depends(get_session_manutencao),
) -> dict:
    global_row = session.exec(
        select(ParametroFazenda).where(ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id.is_(None))
    ).first()
    if not global_row:
        raise HTTPException(status_code=404, detail="Parâmetro não encontrado")

    valor_texto = "true" if (global_row.tipo == "bool" and dados.valor in (True, "true", "sim", "1", 1)) else (
        "false" if global_row.tipo == "bool" else str(dados.valor)
    )
    agora = datetime.utcnow()
    aplicar_em_todas = not dados.fazenda_ids
    alvo_ids = _fazendas_alvo(session, dados.fazenda_ids)

    if aplicar_em_todas:
        global_row.valor = valor_texto
        global_row.atualizado_em = agora
        session.add(global_row)

    existentes = {
        linha.fazenda_id: linha
        for linha in session.exec(
            select(ParametroFazenda).where(ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id.in_(alvo_ids))
        ).all()
    } if alvo_ids else {}

    for fazenda_id in alvo_ids:
        linha = existentes.get(fazenda_id)
        if linha is None:
            linha = ParametroFazenda(
                chave=chave, fazenda_id=fazenda_id, grupo=global_row.grupo, label=global_row.label,
                valor=valor_texto, tipo=global_row.tipo, unidade=global_row.unidade, atualizado_em=agora,
            )
        else:
            linha.valor = valor_texto
            linha.atualizado_em = agora
        session.add(linha)

    session.commit()
    return {"atualizados": len(alvo_ids), "total_fazendas": len(alvo_ids), "global_atualizado": aplicar_em_todas}
