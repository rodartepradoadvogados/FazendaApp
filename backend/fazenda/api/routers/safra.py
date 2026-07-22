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

from fazenda.database import get_session
from fazenda.models import Safra

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
def listar_safras(session: Session = Depends(get_session)) -> list[dict]:
    return [s.model_dump() for s in session.exec(select(Safra).order_by(Safra.data_inicio.desc())).all()]


@router.post("/")
def criar_safra(dados: SafraIn, session: Session = Depends(get_session)) -> dict:
    _validar(dados)
    nome = dados.nome.strip()
    if session.exec(select(Safra).where(Safra.nome == nome)).first():
        raise HTTPException(status_code=400, detail=f"Já existe uma safra com o nome {nome}")
    safra = Safra(**{**dados.model_dump(), "nome": nome, "centro_custo": dados.centro_custo.strip()})
    session.add(safra)
    session.commit()
    session.refresh(safra)
    return safra.model_dump()


@router.put("/{safra_id}")
def atualizar_safra(safra_id: int, dados: SafraIn, session: Session = Depends(get_session)) -> dict:
    _validar(dados)
    safra = session.get(Safra, safra_id)
    if not safra:
        raise HTTPException(status_code=404, detail="Safra não encontrada")
    nome = dados.nome.strip()
    existente = session.exec(select(Safra).where(Safra.nome == nome)).first()
    if existente and existente.id != safra.id:
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
