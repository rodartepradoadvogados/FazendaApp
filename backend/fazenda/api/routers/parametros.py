"""
Router de parâmetros — metas e configurações zootécnicas/financeiras
editáveis (Configurações > Parâmetros).
Endpoints: GET /parametros/ , PUT /parametros/{chave}

Antes de fazenda_id ser considerado aqui, GET devolvia TODAS as linhas de
TODAS as fazendas juntas (nenhum filtro) e PUT editava a primeira linha que
batesse com a chave, também sem filtro — como nada nunca criava uma linha
fazenda-específica, isso na prática significava que toda fazenda-cliente
lia/editava o MESMO parâmetro global (fazenda_id NULL): editar "PEV" numa
fazenda mudava silenciosamente o valor visto por todas as outras. Mesmo
padrão clone-on-write de farmacia.py agora: GET prefere a linha
fazenda-específica e cai no padrão global; PUT edita a linha fazenda-
específica se existir, senão CLONA o padrão global para essa fazenda antes
de aplicar a edição — nunca mais toca a linha global (fazenda_id NULL) a
partir de uma fazenda de verdade. Espelha exatamente a preferência que
`rules.parametros._linha` já usa há mais tempo para leitura de regras de
negócio (get_param/get_param_bool/...), só que agora o router segue a
mesma regra.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, or_, select

from fazenda.auth import exigir_admin, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import ParametroFazenda, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.parametros import GRUPO_TITULOS

router = APIRouter(prefix="/parametros", tags=["parametros"])


def _linha_visivel(session: Session, chave: str, fazenda_id: int | None) -> ParametroFazenda | None:
    if fazenda_id is not None:
        especifica = session.exec(
            select(ParametroFazenda).where(ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == fazenda_id)
        ).first()
        if especifica is not None:
            return especifica
    return session.exec(
        select(ParametroFazenda).where(ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id.is_(None))
    ).first()


@router.get("/")
def obter_parametros(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Parâmetros de manejo, metas e sistema usados como referência nos
    indicadores, na agenda e nos relatórios — agrupados igual à tela.
    Uma linha por chave: a personalização da fazenda atual quando existir,
    senão o padrão global."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    # `IN (fazenda_id, NULL)` NÃO casa com linhas NULL em SQL (IN nunca
    # inclui NULL) — precisa do OR explícito com IS NULL.
    filtro = (
        ParametroFazenda.fazenda_id.is_(None) if fazenda_id is None
        else or_(ParametroFazenda.fazenda_id == fazenda_id, ParametroFazenda.fazenda_id.is_(None))
    )
    todas = session.exec(select(ParametroFazenda).where(filtro).order_by(ParametroFazenda.id)).all()
    por_chave: dict[str, ParametroFazenda] = {}
    for linha in todas:
        # Entre a global (fazenda_id None) e a específica desta fazenda,
        # fica a específica — ordem de inserção não garante qual vem
        # primeiro, então checa explicitamente em vez de só "a última vence".
        atual = por_chave.get(linha.chave)
        if atual is None or (atual.fazenda_id is None and linha.fazenda_id is not None):
            por_chave[linha.chave] = linha

    grupos: dict[str, dict] = {}
    for grupo_id, titulo in GRUPO_TITULOS.items():
        grupos[grupo_id] = {"titulo": titulo, "itens": []}
    for linha in por_chave.values():
        grupo = grupos.setdefault(linha.grupo, {"titulo": linha.grupo, "itens": []})
        valor: float | int | bool | str | None
        if linha.tipo == "bool":
            valor = (linha.valor or "").strip().lower() in ("1", "true", "sim", "yes")
        elif linha.tipo == "date":
            valor = linha.valor
        elif linha.tipo == "float":
            try:
                valor = float(linha.valor)
            except (TypeError, ValueError):
                valor = None
        else:
            try:
                valor = int(float(linha.valor))
            except (TypeError, ValueError):
                valor = None
        grupo["itens"].append({
            "chave": linha.chave, "label": linha.label, "valor": valor,
            "unidade": linha.unidade, "tipo": linha.tipo,
        })
    # Remove grupos sem nenhum item (não deveria acontecer após o seed, mas
    # evita cards vazios antes do primeiro startup rodar o seed).
    grupos = {k: v for k, v in grupos.items() if v["itens"]}
    return {"grupos": grupos}


class AtualizarParametroIn(BaseModel):
    valor: float | int | bool | str


@router.put("/{chave}")
def atualizar_parametro(
    chave: str, dados: AtualizarParametroIn,
    session: Session = Depends(get_session), _: Usuario = Depends(exigir_admin),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Edita o valor de um parâmetro — passa a valer para os relatórios,
    agenda e regras desta fazenda que o leem via get_param(). Sem fazenda_id
    (ex.: Painel CowData fora de modo suporte), edita o padrão global."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    linha = _linha_visivel(session, chave, fazenda_id)
    if not linha:
        raise HTTPException(status_code=404, detail="Parâmetro não encontrado")
    if fazenda_id is not None and linha.fazenda_id is None:
        linha = ParametroFazenda(
            chave=linha.chave, fazenda_id=fazenda_id, grupo=linha.grupo, label=linha.label,
            valor=linha.valor, tipo=linha.tipo, unidade=linha.unidade,
        )
    if linha.tipo == "bool":
        linha.valor = "true" if dados.valor in (True, "true", "sim", "1", 1) else "false"
    else:
        linha.valor = str(dados.valor)
    linha.atualizado_em = datetime.utcnow()
    session.add(linha)
    session.commit()
    return {"ok": True, "chave": chave, "valor": dados.valor}
