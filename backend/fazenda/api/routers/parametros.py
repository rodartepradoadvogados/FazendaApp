"""
Router de parâmetros — metas e configurações zootécnicas/financeiras
editáveis (Configurações > Parâmetros).
Endpoints: GET /parametros/ , PUT /parametros/{chave}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin
from fazenda.database import get_session
from fazenda.models import Usuario
from fazenda.rules.parametros import GRUPO_TITULOS

router = APIRouter(prefix="/parametros", tags=["parametros"])


@router.get("/")
def obter_parametros(session: Session = Depends(get_session)) -> dict:
    """Parâmetros de manejo, metas e sistema usados como referência nos
    indicadores, na agenda e nos relatórios — agrupados igual à tela."""
    from fazenda.models import ParametroFazenda

    linhas = session.exec(select(ParametroFazenda).order_by(ParametroFazenda.id)).all()
    grupos: dict[str, dict] = {}
    for grupo_id, titulo in GRUPO_TITULOS.items():
        grupos[grupo_id] = {"titulo": titulo, "itens": []}
    for linha in linhas:
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
) -> dict:
    """Edita o valor de um parâmetro já existente — passa a valer para todos
    os relatórios, agenda e regras que o leem via get_param()."""
    from datetime import datetime

    from fazenda.models import ParametroFazenda

    linha = session.exec(select(ParametroFazenda).where(ParametroFazenda.chave == chave)).first()
    if not linha:
        raise HTTPException(status_code=404, detail="Parâmetro não encontrado")
    if linha.tipo == "bool":
        linha.valor = "true" if dados.valor in (True, "true", "sim", "1", 1) else "false"
    else:
        linha.valor = str(dados.valor)
    linha.atualizado_em = datetime.utcnow()
    session.add(linha)
    session.commit()
    return {"ok": True, "chave": chave, "valor": dados.valor}
