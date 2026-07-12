"""
Router de estoque — inventário completo de insumos e lançamento de
entradas/saídas (dá baixa ou soma direto em Estoque.quantidade).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Estoque, Fornecedor, MovimentoEstoque

router = APIRouter(prefix="/estoque", tags=["estoque"])

MOVIMENTOS_ENTRADA = ["Entrada de ajuste", "Entrada de cortesia"]
MOVIMENTOS_SAIDA = ["Aplicação", "Saída de ajuste", "Doação"]
MOVIMENTOS_VALIDOS = set(MOVIMENTOS_ENTRADA + MOVIMENTOS_SAIDA)
# Só itens estocáveis podem ser doados ou recebidos de cortesia — itens não
# estocáveis existem só para lançamento financeiro, sem controle de quantidade.
MOVIMENTOS_SOMENTE_ESTOCAVEL = {"Doação", "Entrada de cortesia"}

UNIDADES_EMBALAGEM = ["Saca", "Pote", "Frasco", "Pacote", "Bag", "Fardo", "Garrafa", "Unidade"]
MEDIDAS_EMBALAGEM = ["kg/saca", "litros/garrafa", "mililitros/frasco", "unidades/fardo", "potes/caixa", "unidades"]


@router.get("/")
def listar_estoque(session: Session = Depends(get_session)) -> dict:
    """Todos os itens de estoque para o dashboard interativo (filtra no cliente)."""
    fornecedores = {f.id: f.nome for f in session.exec(select(Fornecedor)).all()}
    itens = [
        {**e.model_dump(), "fornecedor_nome": fornecedores.get(e.fornecedor_id)}
        for e in session.exec(select(Estoque).order_by(Estoque.nome)).all()
    ]
    return {"itens": itens, "total": len(itens)}


class EstoqueIn(BaseModel):
    nome: str
    categoria: str | None = None
    numero_produto: str | None = None
    unidade: str | None = None
    quantidade: float | None = None
    estoque_minimo: float | None = None
    valor_unitario: float | None = None
    local_armazenamento: str | None = None
    unidade_embalagem: str | None = None
    medida_embalagem: str | None = None
    quantidade_embalagem: float | None = None
    fornecedor_id: int | None = None
    ativo: bool = True
    observacao: str | None = None
    carencia_dias: int | None = None
    centro_custo_padrao: str | None = None
    conta_gerencial_despesa_padrao: str | None = None
    conta_gerencial_receita_padrao: str | None = None
    exibir_necessidade_compra_agenda: bool = False
    estocavel: bool = True
    data_inicio_controle: date | None = None
    principio_ativo: str | None = None
    classificacao_medicamento: str | None = None


def _validar_embalagem(unidade_embalagem: str | None, medida_embalagem: str | None) -> None:
    if unidade_embalagem and unidade_embalagem not in UNIDADES_EMBALAGEM:
        raise HTTPException(status_code=400, detail=f"Unidade de embalagem inválida — use uma de: {', '.join(UNIDADES_EMBALAGEM)}")
    if medida_embalagem and medida_embalagem not in MEDIDAS_EMBALAGEM:
        raise HTTPException(status_code=400, detail=f"Unidade de medida inválida — use uma de: {', '.join(MEDIDAS_EMBALAGEM)}")


@router.post("/", status_code=201)
def criar_item_estoque(dados: EstoqueIn, session: Session = Depends(get_session)) -> dict:
    """Cadastra um item de estoque novo (não existe ainda um com esse nome)."""
    existente = session.exec(select(Estoque).where(Estoque.nome == dados.nome)).first()
    if existente:
        raise HTTPException(status_code=409, detail=f'Já existe um item de estoque chamado "{dados.nome}"')
    _validar_embalagem(dados.unidade_embalagem, dados.medida_embalagem)

    valor_total = (dados.quantidade or 0) * (dados.valor_unitario or 0) if dados.quantidade and dados.valor_unitario else None
    item = Estoque(
        nome=dados.nome,
        categoria=dados.categoria,
        numero_produto=dados.numero_produto,
        unidade=dados.unidade,
        quantidade=dados.quantidade,
        estoque_minimo=dados.estoque_minimo,
        valor_unitario=dados.valor_unitario,
        valor_total=valor_total,
        abaixo_minimo=(dados.quantidade is not None and dados.estoque_minimo is not None and dados.quantidade < dados.estoque_minimo),
        local_armazenamento=dados.local_armazenamento,
        unidade_embalagem=dados.unidade_embalagem,
        medida_embalagem=dados.medida_embalagem,
        quantidade_embalagem=dados.quantidade_embalagem,
        fornecedor_id=dados.fornecedor_id,
        ativo=dados.ativo,
        observacao=dados.observacao,
        carencia_dias=dados.carencia_dias,
        centro_custo_padrao=dados.centro_custo_padrao,
        conta_gerencial_despesa_padrao=dados.conta_gerencial_despesa_padrao,
        conta_gerencial_receita_padrao=dados.conta_gerencial_receita_padrao,
        exibir_necessidade_compra_agenda=dados.exibir_necessidade_compra_agenda,
        estocavel=dados.estocavel,
        data_inicio_controle=dados.data_inicio_controle if dados.estocavel else None,
        principio_ativo=dados.principio_ativo,
        classificacao_medicamento=dados.classificacao_medicamento,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.get("/medicamentos")
def listar_medicamentos(
    principio_ativo: str = "", classificacao: str = "",
    session: Session = Depends(get_session),
) -> list[dict]:
    """Medicamentos (itens de estoque) que cumprem um critério — usado ao
    lançar um protocolo cadastrado por princípio ativo ou por classificação."""
    itens = session.exec(select(Estoque)).all()
    saida = []
    for e in itens:
        if principio_ativo and (e.principio_ativo or "").strip().lower() != principio_ativo.strip().lower():
            continue
        if classificacao and (e.classificacao_medicamento or "").strip().lower() != classificacao.strip().lower():
            continue
        saida.append({
            "nome": e.nome, "unidade": e.unidade, "quantidade": e.quantidade,
            "principio_ativo": e.principio_ativo, "classificacao_medicamento": e.classificacao_medicamento,
        })
    return sorted(saida, key=lambda x: x["nome"])


@router.get("/movimentos")
def listar_movimentos(session: Session = Depends(get_session)) -> dict:
    """Histórico de entradas/saídas lançadas manualmente."""
    movs = session.exec(select(MovimentoEstoque).order_by(MovimentoEstoque.data_movimento.desc())).all()
    return {"movimentos": [m.model_dump() for m in movs], "total": len(movs)}


class MovimentoIn(BaseModel):
    nome: str
    movimento: str
    quantidade: float
    unidade: str | None = None
    data_movimento: date
    observacao: str | None = None


@router.post("/movimentar")
def movimentar_estoque(dados: MovimentoIn, session: Session = Depends(get_session)) -> dict:
    if dados.movimento not in MOVIMENTOS_VALIDOS:
        raise HTTPException(status_code=400, detail="Tipo de movimento inválido")
    if dados.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero")

    item = session.exec(select(Estoque).where(Estoque.nome == dados.nome)).first()
    if not item:
        raise HTTPException(status_code=404, detail=f'Item de estoque "{dados.nome}" não encontrado')
    if dados.movimento in MOVIMENTOS_SOMENTE_ESTOCAVEL and item.estocavel is False:
        raise HTTPException(status_code=400, detail="Somente itens estocáveis podem ser doados ou recebidos de cortesia")

    baixa = dados.movimento in MOVIMENTOS_SAIDA
    item.quantidade = (item.quantidade or 0) + (-dados.quantidade if baixa else dados.quantidade)
    if item.estoque_minimo is not None:
        item.abaixo_minimo = item.quantidade < item.estoque_minimo
    item.atualizado_em = datetime.utcnow()
    session.add(item)

    session.add(MovimentoEstoque(
        nome_item=dados.nome,
        movimento=dados.movimento,
        quantidade=dados.quantidade,
        unidade=dados.unidade or item.unidade,
        data_movimento=dados.data_movimento,
        observacao=dados.observacao,
    ))
    session.commit()
    session.refresh(item)
    return item.model_dump()
