"""
Router de Safra — cadastro usado pelo relatório de custo agrícola (Opção A do
plano de custo da silagem, ver relatorio_custo_safra.py). Mesmo padrão de
campos simples de Lote/CentroCusto — sem exclusão direta, só soft-delete via
`ativo` (Configurações > Cadastro > Safra).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import Safra
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/safras", tags=["safras"])


class SafraIn(BaseModel):
    nome: str
    centro_custo: str = "Agricultura"
    data_inicio: date
    data_fim: date
    hectares: float
    toneladas_produzidas: float
    observacao: str | None = None
    ativo: bool = True


def _validar(dados: SafraIn) -> None:
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if not dados.centro_custo.strip():
        raise HTTPException(status_code=400, detail="Centro de custo é obrigatório")
    if dados.data_fim < dados.data_inicio:
        raise HTTPException(status_code=400, detail="Data final não pode ser anterior à data inicial")
    if dados.hectares <= 0:
        raise HTTPException(status_code=400, detail="Hectares deve ser maior que zero")
    if dados.toneladas_produzidas <= 0:
        raise HTTPException(status_code=400, detail="Toneladas produzidas deve ser maior que zero")


@router.get("/")
def listar_safras(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Safra)
    if fazenda_id is not None:
        query = query.where(Safra.fazenda_id == fazenda_id)
    return [s.model_dump() for s in session.exec(query.order_by(Safra.data_inicio.desc())).all()]


@router.post("/")
def criar_safra(
    dados: SafraIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    _validar(dados)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    query_existente = select(Safra).where(Safra.nome == nome)
    if fazenda_id is not None:
        query_existente = query_existente.where(Safra.fazenda_id == fazenda_id)
    if session.exec(query_existente).first():
        raise HTTPException(status_code=400, detail=f"Já existe uma safra com o nome {nome}")
    safra = Safra(**{**dados.model_dump(), "nome": nome, "centro_custo": dados.centro_custo.strip(), "fazenda_id": fazenda_id})
    session.add(safra)
    session.commit()
    session.refresh(safra)
    return safra.model_dump()


@router.put("/{safra_id}")
def atualizar_safra(
    safra_id: int, dados: SafraIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    _validar(dados)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    safra = session.get(Safra, safra_id)
    if not safra or (fazenda_id is not None and safra.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Safra não encontrada")
    nome = dados.nome.strip()
    query_existente = select(Safra).where(Safra.nome == nome, Safra.id != safra.id)
    if fazenda_id is not None:
        query_existente = query_existente.where(Safra.fazenda_id == fazenda_id)
    existente = session.exec(query_existente).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"Já existe uma safra com o nome {nome}")

    safra.nome = nome
    safra.centro_custo = dados.centro_custo.strip()
    safra.data_inicio = dados.data_inicio
    safra.data_fim = dados.data_fim
    safra.hectares = dados.hectares
    safra.toneladas_produzidas = dados.toneladas_produzidas
    safra.observacao = dados.observacao
    safra.ativo = dados.ativo
    safra.atualizado_em = datetime.utcnow()
    session.add(safra)
    session.commit()
    session.refresh(safra)
    return safra.model_dump()
