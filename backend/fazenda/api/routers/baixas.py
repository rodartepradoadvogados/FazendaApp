"""
Router de baixa de animal (Rebanho > Baixar animal) — óbito/descarte
definitivo do rebanho, distinto de movimentação entre lotes. Ao registrar,
o(s) animal(is) selecionado(s) ficam inativos (Animal.ativo = False).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, BaixaAnimal

router = APIRouter(prefix="/baixas", tags=["baixas"])

TIPOS_BAIXA = ["morte", "descarte_voluntario", "descarte_involuntario"]
MOTIVOS = ["venda", "abate", "acidente", "doenca"]

# Lista de doenças/causas — usada só como referência no front (select); o
# backend aceita qualquer texto não vazio em motivo_doenca.
MOTIVOS_DOENCA = [
    "Botulismo", "Brucelose", "Tuberculose", "Babesia", "Casco", "Choque anafilático",
    "Afogada", "Complicações pós-parto", "Clostridiose", "Descarga elétrica", "Descarte",
    "Deslocamento de abomaso", "Desconhecido", "Diarréia", "Doação", "Doenças a vírus",
    "Doenças bacterianas", "Doenças", "Fratura", "Hemorragia interna", "Hipocalcemia",
    "Idade avançada", "Infarto", "Ingestão de corpo estranho", "Intoxicação", "Leptospirose",
    "Má formação", "Mastite", "Metrite", "Morte natural", "Nascimento prematuro", "Natimorto",
    "Pneumonia", "Retenção de placenta", "Roubo", "Tripanossoma", "Trombose",
]


class BaixaIn(BaseModel):
    animais: list[str]
    tipo_baixa: str
    motivo: str
    motivo_doenca: str | None = None
    valor: float | None = None
    cliente: str | None = None
    data_baixa: date
    observacao: str | None = None
    responsavel: str | None = None


@router.get("/motivos")
def listar_opcoes() -> dict:
    return {"tipos_baixa": TIPOS_BAIXA, "motivos": MOTIVOS, "motivos_doenca": MOTIVOS_DOENCA}


@router.get("/")
def listar_baixas(session: Session = Depends(get_session)) -> list[dict]:
    baixas = session.exec(select(BaixaAnimal).order_by(BaixaAnimal.data_baixa.desc(), BaixaAnimal.id.desc())).all()
    return [b.model_dump() for b in baixas]


@router.post("/")
def registrar_baixa(dados: BaixaIn, session: Session = Depends(get_session)) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")
    if dados.tipo_baixa not in TIPOS_BAIXA:
        raise HTTPException(status_code=400, detail="Tipo de baixa inválido")
    if dados.motivo not in MOTIVOS:
        raise HTTPException(status_code=400, detail="Motivo inválido")
    if dados.motivo == "doenca" and not (dados.motivo_doenca or "").strip():
        raise HTTPException(status_code=400, detail="Informe a doença/causa")
    if dados.motivo == "venda" and (dados.valor is None or not (dados.cliente or "").strip()):
        raise HTTPException(status_code=400, detail="Venda exige valor e cliente")

    baixados = []
    nao_encontrados = []
    for numero in dados.animais:
        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if not animal:
            nao_encontrados.append(numero)
            continue

        session.add(BaixaAnimal(
            numero_animal=numero, tipo_baixa=dados.tipo_baixa, motivo=dados.motivo,
            motivo_doenca=dados.motivo_doenca if dados.motivo == "doenca" else None,
            valor=dados.valor if dados.motivo == "venda" else None,
            cliente=dados.cliente if dados.motivo == "venda" else None,
            data_baixa=dados.data_baixa, observacao=dados.observacao, responsavel=dados.responsavel,
        ))

        animal.ativo = False
        animal.data_baixa = dados.data_baixa
        animal.motivo_baixa = dados.motivo_doenca if dados.motivo == "doenca" else dados.motivo
        animal.atualizado_em = datetime.utcnow()
        session.add(animal)
        baixados.append(numero)

    session.commit()
    return {"baixados": len(baixados), "animais": baixados, "nao_encontrados": nao_encontrados}
