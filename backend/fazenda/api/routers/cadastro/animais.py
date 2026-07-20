"""
Cadastro > Animais — ficha do animal (grava na tabela Animal usada em todo o
site), motivo de baixa, motivo de venda, raça e grau de sangue.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, GrauSangue, MotivoBaixa, MotivoVenda, Raca

from ._comum import _crud_nome_ativo

router = APIRouter()

# ---------------------------------------------------------------------------
# Ficha do animal — grava direto na tabela Animal usada em todo o site.
# ---------------------------------------------------------------------------
class AnimalFichaIn(BaseModel):
    numero: str
    nome: str | None = None
    sisbov: str | None = None
    sexo: str | None = None  # "F" | "M"
    raca: str | None = None
    grau_sangue: str | None = None
    categoria_abrev: str | None = None
    grupo_primario: str | None = None
    data_nasc: date | None = None
    data_entrada: date | None = None
    proprietario: str | None = None
    valor: float | None = None
    motivo_baixa: str | None = None
    data_baixa: date | None = None
    mae_numero: str | None = None
    mae_nome: str | None = None
    pai_nome: str | None = None
    pai_naab: str | None = None
    avo_paterno_nome: str | None = None
    avo_paterno_naab: str | None = None
    bisavo_paterno_nome: str | None = None
    bisavo_paterno_naab: str | None = None
    observacoes: str | None = None
    excluir_bst: bool = False


def _completar_genealogia_paterna(session: Session, animal: Animal) -> None:
    """Se o pai foi informado mas a genealogia paterna (avô/bisavô) não foi
    preenchida manualmente, tenta buscá-la no cadastro do animal — o pai pode
    também estar cadastrado como Animal (touro da fazenda) com sua própria
    genealogia já registrada; o avô, idem, uma geração acima. Sem essa cadeia
    cadastrada não há como derivar automaticamente — quem chama decide se
    deixa em aberto para seleção manual."""
    if animal.pai_nome and not animal.avo_paterno_nome:
        pai_animal = session.exec(
            select(Animal).where(func.lower(Animal.nome) == animal.pai_nome.strip().lower())
        ).first()
        if pai_animal and pai_animal.pai_nome:
            animal.avo_paterno_nome = pai_animal.pai_nome
            animal.avo_paterno_naab = pai_animal.pai_naab
    if animal.avo_paterno_nome and not animal.bisavo_paterno_nome:
        avo_animal = session.exec(
            select(Animal).where(func.lower(Animal.nome) == animal.avo_paterno_nome.strip().lower())
        ).first()
        if avo_animal and avo_animal.pai_nome:
            animal.bisavo_paterno_nome = avo_animal.pai_nome
            animal.bisavo_paterno_naab = avo_animal.pai_naab


@router.post("/animais")
def criar_animal(dados: AnimalFichaIn, session: Session = Depends(get_session)) -> dict:
    numero = dados.numero.strip()
    if not numero:
        raise HTTPException(status_code=400, detail="Número/brinco é obrigatório")
    existente = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"Já existe um animal com o número {numero}")

    animal = Animal(numero=numero, ativo=dados.data_baixa is None)
    for campo, valor in dados.model_dump(exclude={"numero"}).items():
        setattr(animal, campo, valor)
    _completar_genealogia_paterna(session, animal)
    session.add(animal)
    session.commit()
    session.refresh(animal)
    return animal.model_dump()


@router.put("/animais/{numero}")
def atualizar_ficha_animal(numero: str, dados: AnimalFichaIn, session: Session = Depends(get_session)) -> dict:
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    for campo, valor in dados.model_dump(exclude={"numero"}).items():
        setattr(animal, campo, valor)
    if dados.data_baixa is not None:
        animal.ativo = False
    _completar_genealogia_paterna(session, animal)
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    session.commit()
    session.refresh(animal)
    return animal.model_dump()



# ---------------------------------------------------------------------------
# Motivo de baixa (Rebanho > Baixar animal) — causa específica da baixa (usada
# quando o motivo geral é "doença", mas também cobre outras causas comuns:
# acidente, roubo, idade avançada etc.). Cadastrável em Configurações, para
# não ficar limitado à lista fixa que havia antes só no código.
# ---------------------------------------------------------------------------
SEED_MOTIVOS_BAIXA = [
    "Botulismo", "Brucelose", "Tuberculose", "Babesia", "Casco", "Choque anafilático",
    "Afogada", "Complicações pós-parto", "Clostridiose", "Descarga elétrica", "Descarte",
    "Deslocamento de abomaso", "Desconhecido", "Diarréia", "Doação", "Doenças a vírus",
    "Doenças bacterianas", "Doenças", "Fratura", "Hemorragia interna", "Hipocalcemia",
    "Idade avançada", "Infarto", "Ingestão de corpo estranho", "Intoxicação", "Leptospirose",
    "Má formação", "Mastite", "Metrite", "Morte natural", "Nascimento prematuro", "Natimorto",
    "Pneumonia", "Retenção de placenta", "Roubo", "Tripanossoma", "Trombose",
]


def seed_motivos_baixa(session: Session) -> None:
    """Cria os motivos de baixa padrão se a tabela ainda estiver vazia (idempotente)."""
    if session.exec(select(MotivoBaixa)).first():
        return
    for nome in SEED_MOTIVOS_BAIXA:
        session.add(MotivoBaixa(nome=nome))
    session.commit()


# ---------------------------------------------------------------------------
# Motivos de venda de animal (Lançamentos > Compra/Venda > Vender animal) —
# lista padrão razoável, editável depois em Configurações > Parâmetros >
# Parâmetros gerais.
# ---------------------------------------------------------------------------
SEED_MOTIVOS_VENDA = [
    "Descarte (baixa produção)", "Problema reprodutivo", "Problema sanitário/mastite crônica",
    "Excedente de rebanho", "Venda de touro/reprodutor", "Venda de recria/leite para outra propriedade",
    "Idade avançada", "Seleção genética", "Comportamento/temperamento", "Ajuste de fluxo de caixa",
]


def seed_motivos_venda(session: Session) -> None:
    """Cria os motivos de venda padrão se a tabela ainda estiver vazia (idempotente)."""
    if session.exec(select(MotivoVenda)).first():
        return
    for nome in SEED_MOTIVOS_VENDA:
        session.add(MotivoVenda(nome=nome))
    session.commit()


# ---------------------------------------------------------------------------
# Raça e Grau de sangue — cadastráveis em Configurações, substituindo o select
# fixo (Girolando/Holandês/Gir/Outra) e o datalist de grau de sangue que
# existiam hardcoded em CadastroAnimalForm. `fracao_holandes` de cada grau de
# sangue é a posição na escala de absorção Holandês x Gir (0 = PO Gir, 1 = PO
# Holandês) — usada para calcular automaticamente o grau de sangue da cria no
# parto (ver calcular_grau_sangue_cria em fazenda.rules.genetica).
# ---------------------------------------------------------------------------
SEED_RACAS = ["Girolando", "Holandês", "Gir", "Jersey", "Outra"]

SEED_GRAUS_SANGUE = [
    ("PO Gir", 0.0),
    ("1/2 Holandês x Gir", 0.5),
    ("3/4 Holandês", 0.75),
    ("7/8 Holandês", 0.875),
    ("15/16 Holandês", 0.9375),
    ("31/32 Holandês", 0.96875),
    ("PCOD Holandês", None),
    ("PO Holandês", 1.0),
]


def seed_racas_grau_sangue(session: Session) -> None:
    """Cria as raças e graus de sangue padrão se as tabelas ainda estiverem vazias (idempotente)."""
    if not session.exec(select(Raca)).first():
        for nome in SEED_RACAS:
            session.add(Raca(nome=nome))
        session.commit()
    if not session.exec(select(GrauSangue)).first():
        for nome, fracao in SEED_GRAUS_SANGUE:
            session.add(GrauSangue(nome=nome, fracao_holandes=fracao))
        session.commit()



_listar_motivos_baixa, _criar_motivo_baixa, _atualizar_motivo_baixa = _crud_nome_ativo(MotivoBaixa)
router.get("/motivos-baixa")(_listar_motivos_baixa)
router.post("/motivos-baixa")(_criar_motivo_baixa)
router.put("/motivos-baixa/{item_id}")(_atualizar_motivo_baixa)

_listar_motivos_venda, _criar_motivo_venda, _atualizar_motivo_venda = _crud_nome_ativo(MotivoVenda)
router.get("/motivos-venda")(_listar_motivos_venda)
router.post("/motivos-venda")(_criar_motivo_venda)
router.put("/motivos-venda/{item_id}")(_atualizar_motivo_venda)


_listar_racas, _criar_raca, _atualizar_raca = _crud_nome_ativo(Raca)
router.get("/racas")(_listar_racas)
router.post("/racas")(_criar_raca)
router.put("/racas/{item_id}")(_atualizar_raca)


class GrauSangueIn(BaseModel):
    nome: str
    fracao_holandes: Optional[float] = None
    ativo: bool = True


@router.get("/graus-sangue")
def listar_graus_sangue(session: Session = Depends(get_session)) -> list[dict]:
    return [g.model_dump() for g in session.exec(select(GrauSangue).order_by(GrauSangue.id)).all()]


@router.post("/graus-sangue")
def criar_grau_sangue(dados: GrauSangueIn, session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if session.exec(select(GrauSangue).where(GrauSangue.nome == nome)).first():
        raise HTTPException(status_code=409, detail=f"Já existe um grau de sangue com o nome '{nome}'")
    obj = GrauSangue(nome=nome, fracao_holandes=dados.fracao_holandes, ativo=dados.ativo)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.put("/graus-sangue/{item_id}")
def atualizar_grau_sangue(item_id: int, dados: GrauSangueIn, session: Session = Depends(get_session)) -> dict:
    obj = session.get(GrauSangue, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Grau de sangue não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    obj.nome = nome
    obj.fracao_holandes = dados.fracao_holandes
    obj.ativo = dados.ativo
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()



