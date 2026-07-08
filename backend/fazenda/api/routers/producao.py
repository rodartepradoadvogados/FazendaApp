"""
Router de produção — indicadores do histórico de controle leiteiro e
lançamento de pesagens (por vaca ou por lote inteiro, de uma vez).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, ControleLeiteiro, PesagemCorporal
from fazenda.rules.producao import calcular_producao

router = APIRouter(prefix="/producao", tags=["producao"])


class OrdenhaIn(BaseModel):
    numero_matriz: str
    ordenhas: list[float]


class ControlesIn(BaseModel):
    data_controle: date
    entradas: list[OrdenhaIn]


@router.get("/")
def obter_producao(session: Session = Depends(get_session)) -> dict:
    """Série temporal, curva de lactação e ranking por vaca do controle leiteiro."""
    controles = [c.model_dump() for c in session.exec(select(ControleLeiteiro)).all()]
    return calcular_producao(controles)


@router.get("/controles")
def listar_controles(session: Session = Depends(get_session)) -> dict:
    """Registros de controle leiteiro achatados para o dashboard interativo."""
    registros = []
    for c in session.exec(select(ControleLeiteiro)).all():
        d = c.data_controle
        registros.append({
            "numero": c.numero_matriz,
            "raca": c.raca or "(sem raça)",
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "producao_kg": c.producao_kg,
            "del": c.del_no_controle,
        })
    return {"controles": registros, "total": len(registros)}


@router.post("/controles")
def criar_controles(dados: ControlesIn, session: Session = Depends(get_session)) -> dict:
    """
    Registra a pesagem do dia para uma ou várias vacas de uma vez (lançamento
    individual ou em lote — o front manda uma entrada por vaca do lote).
    """
    criados = []
    for entrada in dados.entradas:
        if not entrada.ordenhas or not any(entrada.ordenhas):
            continue
        animal = session.exec(select(Animal).where(Animal.numero == entrada.numero_matriz)).first()
        registro = ControleLeiteiro(
            animal_id=animal.id if animal else None,
            numero_matriz=entrada.numero_matriz,
            raca=animal.raca if animal else None,
            data_controle=dados.data_controle,
            producao_kg=round(sum(entrada.ordenhas), 2),
            del_no_controle=animal.del_dias if animal else None,
        )
        session.add(registro)
        criados.append(registro)
    session.commit()
    return {"criados": len(criados)}


class PesoIn(BaseModel):
    numero_matriz: str
    peso_kg: float


class PesagensIn(BaseModel):
    data_pesagem: date
    entradas: list[PesoIn]


@router.post("/pesagens")
def criar_pesagens(dados: PesagensIn, session: Session = Depends(get_session)) -> dict:
    """Registra a pesagem corporal do dia para uma ou várias vacas de uma vez."""
    criados = []
    for entrada in dados.entradas:
        if not entrada.peso_kg:
            continue
        animal = session.exec(select(Animal).where(Animal.numero == entrada.numero_matriz)).first()
        registro = PesagemCorporal(
            numero_matriz=entrada.numero_matriz,
            data_pesagem=dados.data_pesagem,
            peso_kg=entrada.peso_kg,
            del_dias=animal.del_dias if animal else None,
            idade_meses=animal.idade_meses if animal else None,
            grupo_primario=animal.grupo_primario if animal else None,
        )
        session.add(registro)
        criados.append(registro)
    session.commit()
    return {"criados": len(criados)}


@router.get("/pesagens/relatorio")
def relatorio_pesagens(
    numero_matriz: str | None = None,
    grupo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """
    Primeira/última pesagem, GMD (ganho médio diário — peso final vs inicial no
    período) e GPD (ganho de peso diário entre pesagens — média dos ganhos
    diários de cada intervalo consecutivo) por animal, lote ou todo o rebanho.
    """
    query = select(PesagemCorporal)
    if numero_matriz:
        query = query.where(PesagemCorporal.numero_matriz == numero_matriz)
    if data_inicio:
        query = query.where(PesagemCorporal.data_pesagem >= data_inicio)
    if data_fim:
        query = query.where(PesagemCorporal.data_pesagem <= data_fim)
    pesagens = session.exec(query).all()
    if grupo:
        pesagens = [p for p in pesagens if p.grupo_primario == grupo]

    por_animal: dict[str, list[PesagemCorporal]] = {}
    for p in pesagens:
        por_animal.setdefault(p.numero_matriz, []).append(p)

    linhas = []
    for numero, lista in por_animal.items():
        lista.sort(key=lambda p: p.data_pesagem)
        primeira, ultima = lista[0], lista[-1]
        dias_totais = (ultima.data_pesagem - primeira.data_pesagem).days
        gmd = round((ultima.peso_kg - primeira.peso_kg) / dias_totais, 3) if dias_totais > 0 else None

        taxas = []
        for anterior, atual in zip(lista, lista[1:]):
            dias = (atual.data_pesagem - anterior.data_pesagem).days
            if dias > 0:
                taxas.append((atual.peso_kg - anterior.peso_kg) / dias)
        gpd = round(sum(taxas) / len(taxas), 3) if taxas else None

        linhas.append({
            "numero_matriz": numero,
            "grupo_primario": ultima.grupo_primario,
            "primeira_data": primeira.data_pesagem.isoformat(),
            "primeira_peso": primeira.peso_kg,
            "ultima_data": ultima.data_pesagem.isoformat(),
            "ultima_peso": ultima.peso_kg,
            "gmd_kg_dia": gmd,
            "gpd_kg_dia": gpd,
            "num_pesagens": len(lista),
        })

    linhas.sort(key=lambda l: l["numero_matriz"])
    return {"linhas": linhas, "total": len(linhas)}
