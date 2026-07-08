"""
Router de lotes — cadastro de lotes de manejo e seus parâmetros
(faixa de DEL e de produção), usados hoje pela tela de Configurações >
Cadastro e, no futuro, pelo motor de sugestão automática de movimentação.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, Lote

router = APIRouter(prefix="/lotes", tags=["lotes"])


def _rotulo(codigo: str, nome: str) -> str:
    return f"{codigo} - {nome}"


class LoteIn(BaseModel):
    codigo: str
    nome: str
    del_min: int | None = None
    del_max: int | None = None
    producao_min: float | None = None
    producao_max: float | None = None


def _validar_faixas(dados: LoteIn) -> None:
    if dados.del_min is not None and dados.del_max is not None and dados.del_min > dados.del_max:
        raise HTTPException(status_code=400, detail="DEL mínimo não pode ser maior que o DEL máximo")
    if (
        dados.producao_min is not None
        and dados.producao_max is not None
        and dados.producao_min > dados.producao_max
    ):
        raise HTTPException(status_code=400, detail="Produção mínima não pode ser maior que a máxima")


@router.get("/")
def listar_lotes(session: Session = Depends(get_session)) -> list[dict]:
    lotes = session.exec(select(Lote).order_by(Lote.codigo)).all()
    animais = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
    contagem: dict[str, int] = {}
    for a in animais:
        if a.eh_semen or a.sexo == "M" or not a.grupo_primario:
            continue
        codigo = a.grupo_primario[:2] if a.grupo_primario[:2].isdigit() else a.grupo_primario
        contagem[codigo] = contagem.get(codigo, 0) + 1

    saida = []
    for lote in lotes:
        d = lote.model_dump()
        d["rotulo"] = _rotulo(lote.codigo, lote.nome)
        d["qtd_animais"] = contagem.get(lote.codigo, 0)
        saida.append(d)
    return saida


@router.post("/")
def criar_lote(dados: LoteIn, session: Session = Depends(get_session)) -> dict:
    _validar_faixas(dados)
    codigo = dados.codigo.strip()
    if not codigo or not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Código e nome são obrigatórios")
    existente = session.exec(select(Lote).where(Lote.codigo == codigo)).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"Já existe um lote com o código {codigo}")

    lote = Lote(
        codigo=codigo,
        nome=dados.nome.strip(),
        del_min=dados.del_min,
        del_max=dados.del_max,
        producao_min=dados.producao_min,
        producao_max=dados.producao_max,
    )
    session.add(lote)
    session.commit()
    session.refresh(lote)
    return lote.model_dump()


@router.put("/{lote_id}")
def atualizar_lote(lote_id: int, dados: LoteIn, session: Session = Depends(get_session)) -> dict:
    _validar_faixas(dados)
    lote = session.get(Lote, lote_id)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado")

    nome_antigo = lote.nome
    lote.nome = dados.nome.strip() or lote.nome
    lote.del_min = dados.del_min
    lote.del_max = dados.del_max
    lote.producao_min = dados.producao_min
    lote.producao_max = dados.producao_max
    lote.atualizado_em = datetime.utcnow()
    session.add(lote)

    # Renomeou o lote: atualiza o rótulo de todos os animais que estão nele hoje,
    # para o cadastro e o rebanho não ficarem com nomes divergentes.
    if lote.nome != nome_antigo:
        rotulo_novo = _rotulo(lote.codigo, lote.nome)
        animais = session.exec(select(Animal).where(Animal.grupo_primario != None)).all()  # noqa: E711
        for a in animais:
            if (a.grupo_primario or "")[:2] == lote.codigo:
                a.grupo_primario = rotulo_novo
                session.add(a)

    session.commit()
    session.refresh(lote)
    return lote.model_dump()
