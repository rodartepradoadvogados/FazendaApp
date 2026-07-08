"""
Router de movimentação de animais entre lotes — transferência manual
(individual ou em lote) com data, hora e motivo, e histórico/relatório.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.lotes import coletar_dados_criterios
from fazenda.database import get_session
from fazenda.models import Animal, Lote, MovimentoLote
from fazenda.rules.lote_criterios import lote_tem_criterio, sugerir_movimentacoes

router = APIRouter(prefix="/movimentacoes", tags=["movimentacoes"])

MOTIVOS = [
    "Crescimento",
    "Desmama",
    "Aptidão",
    "Inseminação",
    "Pré-parto",
    "Parto",
    "Aumento de DEL e/ou produção",
    "Final de DEL ou queda de produção",
    "Tratamento/doença",
]


def _rotulo(codigo: str, nome: str) -> str:
    return f"{codigo} - {nome}"


class MoverIn(BaseModel):
    data_movimento: date
    hora_movimento: str | None = None
    motivo: str
    observacao: str | None = None
    responsavel: str | None = None
    lote_destino_codigo: str
    animais: list[str]


@router.get("/motivos")
def listar_motivos() -> list[str]:
    return MOTIVOS


@router.get("/sugestoes")
def sugestoes_movimentacao(session: Session = Depends(get_session)) -> dict:
    """
    Sugestão automática de movimentação entre lotes: usa os critérios já
    cadastrados em cada lote (Configurações > Cadastro > Lotes) — não pede
    nenhum parâmetro novo. Só considera lotes com pelo menos um critério
    definido; um lote sem nenhum critério "atenderia" o rebanho inteiro, então
    fica de fora da comparação.
    """
    hoje = date.today()
    lotes = session.exec(select(Lote)).all()
    animais, servicos_por_animal, sanidades_por_animal, peso_por_animal = coletar_dados_criterios(session)

    sugestoes = sugerir_movimentacoes(lotes, animais, hoje, peso_por_animal, servicos_por_animal, sanidades_por_animal)
    return {
        "sugestoes": sugestoes,
        "total": len(sugestoes),
        "lotes_com_criterio": sum(1 for l in lotes if lote_tem_criterio(l)),
    }


@router.get("/")
def listar_movimentacoes(
    numero_matriz: str | None = Query(None),
    data_inicio: date | None = Query(None),
    data_fim: date | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(MovimentoLote)
    if numero_matriz:
        query = query.where(MovimentoLote.numero_matriz.contains(numero_matriz))
    if data_inicio:
        query = query.where(MovimentoLote.data_movimento >= data_inicio)
    if data_fim:
        query = query.where(MovimentoLote.data_movimento <= data_fim)
    movs = session.exec(query.order_by(MovimentoLote.data_movimento.desc(), MovimentoLote.id.desc())).all()
    return [m.model_dump() for m in movs]


@router.post("/mover")
def mover_animais(dados: MoverIn, session: Session = Depends(get_session)) -> dict:
    if dados.motivo not in MOTIVOS:
        raise HTTPException(status_code=400, detail="Motivo inválido")
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    destino = session.exec(select(Lote).where(Lote.codigo == dados.lote_destino_codigo)).first()
    if not destino:
        raise HTTPException(status_code=404, detail="Lote de destino não encontrado")
    rotulo_destino = _rotulo(destino.codigo, destino.nome)

    movidos = 0
    nao_encontrados = []
    for numero in dados.animais:
        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if not animal:
            nao_encontrados.append(numero)
            continue

        origem = animal.grupo_primario
        animal.grupo_primario = rotulo_destino
        animal.grupo_raw = rotulo_destino
        animal.grupo_manual = True
        animal.atualizado_em = datetime.utcnow()
        session.add(animal)

        session.add(MovimentoLote(
            numero_matriz=numero,
            lote_origem=origem,
            lote_destino=rotulo_destino,
            data_movimento=dados.data_movimento,
            hora_movimento=dados.hora_movimento,
            motivo=dados.motivo,
            observacao=dados.observacao,
            responsavel=dados.responsavel,
        ))
        movidos += 1

    session.commit()
    return {"movidos": movidos, "nao_encontrados": nao_encontrados}
