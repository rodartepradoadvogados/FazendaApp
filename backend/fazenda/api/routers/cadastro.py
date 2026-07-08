"""
Router de Cadastro (Configurações > Cadastro) — dados mestres que antes viviam
misturados em Lançamentos: ficha do animal, fornecedores/fabricantes/clientes
e metadados de itens de estoque (ensacado/kg por saco/fornecedor) usados pela
Alimentação. Lotes já tinham seu próprio router (lotes.py); Fornecedor e a
ficha do animal gravam nas MESMAS tabelas (Animal, Estoque) usadas em todo o
site — não há tabela paralela/inerte.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, Estoque, Fornecedor

router = APIRouter(prefix="/cadastro", tags=["cadastro"])


# ---------------------------------------------------------------------------
# Fornecedores / fabricantes / clientes
# ---------------------------------------------------------------------------
class FornecedorIn(BaseModel):
    nome: str
    tipo: str  # "fornecedor" | "fabricante" | "cliente"
    categoria: str | None = None
    cnpj_cpf: str | None = None
    telefone: str | None = None
    email: str | None = None
    observacoes: str | None = None
    ativo: bool = True


@router.get("/fornecedores")
def listar_fornecedores(session: Session = Depends(get_session)) -> list[dict]:
    return [f.model_dump() for f in session.exec(select(Fornecedor).order_by(Fornecedor.nome)).all()]


@router.post("/fornecedores")
def criar_fornecedor(dados: FornecedorIn, session: Session = Depends(get_session)) -> dict:
    if dados.tipo not in ("fornecedor", "fabricante", "cliente"):
        raise HTTPException(status_code=400, detail="Tipo inválido")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    f = Fornecedor(**dados.model_dump())
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.model_dump()


@router.put("/fornecedores/{fornecedor_id}")
def atualizar_fornecedor(fornecedor_id: int, dados: FornecedorIn, session: Session = Depends(get_session)) -> dict:
    if dados.tipo not in ("fornecedor", "fabricante", "cliente"):
        raise HTTPException(status_code=400, detail="Tipo inválido")
    f = session.get(Fornecedor, fornecedor_id)
    if not f:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    for campo, valor in dados.model_dump().items():
        setattr(f, campo, valor)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f.model_dump()


# ---------------------------------------------------------------------------
# Ficha do animal — grava direto na tabela Animal usada em todo o site.
# ---------------------------------------------------------------------------
class AnimalFichaIn(BaseModel):
    numero: str
    nome: str | None = None
    sisbov: str | None = None
    sexo: str | None = None  # "F" | "M"
    raca: str | None = None
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
    observacoes: str | None = None


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
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    session.commit()
    session.refresh(animal)
    return animal.model_dump()


# ---------------------------------------------------------------------------
# Metadados de itens de estoque — usados pela Alimentação (ensacado/kg por
# saco) e para vincular um fornecedor ao item. A quantidade em si continua
# vindo do ESTOQUE.csv / movimentações; aqui só descrevemos o item.
# ---------------------------------------------------------------------------
class EstoqueMetaIn(BaseModel):
    ensacado: bool | None = None
    kg_por_saco: float | None = None
    fornecedor_id: int | None = None


@router.get("/estoque-itens")
def listar_itens_estoque(session: Session = Depends(get_session)) -> list[dict]:
    return [e.model_dump() for e in session.exec(select(Estoque).order_by(Estoque.nome)).all()]


@router.put("/estoque-itens/{item_id}")
def atualizar_meta_estoque(item_id: int, dados: EstoqueMetaIn, session: Session = Depends(get_session)) -> dict:
    item = session.get(Estoque, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    if dados.fornecedor_id is not None and not session.get(Fornecedor, dados.fornecedor_id):
        raise HTTPException(status_code=400, detail="Fornecedor não encontrado")
    item.ensacado = dados.ensacado
    item.kg_por_saco = dados.kg_por_saco
    item.fornecedor_id = dados.fornecedor_id
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()
