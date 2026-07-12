"""
Router de compra de animal (Rebanho > Comprar animal) — registra apenas o
efeito financeiro/histórico da aquisição (despesa em ContaGerencial +
comissão de corretagem opcional). Não cria nem exige ficha de Animal: o
cadastro do animal em si segue seu próprio fluxo (CSV/ficha), este endpoint
só documenta a compra e gera o lançamento financeiro correspondente.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import Animal, CompraAnimal, ContaGerencial
from fazenda.api.routers.financeiro import _proximo_numero_lancamento
from fazenda.rules.comissao import FORMAS_COMISSAO, criar_comissao

router = APIRouter(prefix="/compras-animais", tags=["compras-animais"])

TIPOS_VALOR = ("por_animal", "total")


class CompraIn(BaseModel):
    animais: list[str]
    vendedor: str
    valor: float
    tipo_valor: str  # "por_animal" | "total"
    data_compra: date
    observacao: str | None = None
    responsavel: str | None = None
    pagar_comissao: bool = False
    corretor_nome: str | None = None
    valor_comissao: float | None = None
    forma_comissao: str | None = None  # "redirecionado" | "separado"


@router.get("/")
def listar_compras(session: Session = Depends(get_session)) -> list[dict]:
    compras = session.exec(select(CompraAnimal).order_by(CompraAnimal.data_compra.desc(), CompraAnimal.id.desc())).all()
    return [c.model_dump() for c in compras]


@router.post("/")
def registrar_compra(dados: CompraIn, session: Session = Depends(get_session)) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Informe ao menos um animal")
    if not (dados.vendedor or "").strip():
        raise HTTPException(status_code=400, detail="Informe o vendedor")
    if dados.valor is None or dados.valor <= 0:
        raise HTTPException(status_code=400, detail="Informe o valor da compra")
    if dados.tipo_valor not in TIPOS_VALOR:
        raise HTTPException(status_code=400, detail="Informe se o valor é por animal ou total")
    if dados.pagar_comissao:
        if not (dados.corretor_nome or "").strip() or not dados.valor_comissao or dados.valor_comissao <= 0:
            raise HTTPException(status_code=400, detail="Informe corretor e valor da comissão")
        if dados.forma_comissao not in FORMAS_COMISSAO:
            raise HTTPException(status_code=400, detail="Informe a forma de pagamento da comissão")

    quantidade = len(dados.animais)
    if dados.tipo_valor == "por_animal":
        valor_unitario = round(dados.valor, 2)
        valor_total = round(valor_unitario * quantidade, 2)
    else:
        valor_total = round(dados.valor, 2)
        valor_unitario = round(valor_total / quantidade, 2)

    numero_lancamento = _proximo_numero_lancamento(session, dados.data_compra.year)
    session.add(ContaGerencial(
        numero_lancamento=numero_lancamento,
        descricao=f"Compra de {quantidade} animal(is) — {dados.vendedor}",
        data_vencimento=dados.data_compra,
        data_competencia=dados.data_compra,
        fornecedor_cliente=dados.vendedor,
        tipo_documento="Compra de animal",
        quantidade=quantidade,
        valor_unitario=valor_unitario,
        valor_total=valor_total,
        parcela_num=1, parcela_total=1,
        tipo="despesa", origem="auto",
    ))

    if dados.pagar_comissao:
        criar_comissao(
            session,
            origem_tipo="compra_animal",
            numero_lancamento_origem=numero_lancamento,
            corretor_nome=dados.corretor_nome,
            valor_comissao=dados.valor_comissao,
            forma=dados.forma_comissao,
            data_transacao=dados.data_compra,
            descricao_origem=f"compra de {quantidade} animal(is) de {dados.vendedor}",
        )

    comprados = []
    for numero in dados.animais:
        session.add(CompraAnimal(
            numero_animal=numero, vendedor=dados.vendedor, valor=valor_unitario,
            tipo_valor=dados.tipo_valor, data_compra=dados.data_compra,
            responsavel=dados.responsavel, observacao=dados.observacao,
            numero_lancamento_gerado=numero_lancamento,
        ))
        # Vincula o valor da compra à ficha do animal (para o relatório de
        # payback quando ele produzir). Preenche data de entrada e vendedor.
        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if animal:
            animal.valor = valor_unitario
            if not animal.data_entrada:
                animal.data_entrada = dados.data_compra
            if not animal.proprietario:
                animal.proprietario = dados.vendedor
            session.add(animal)
        comprados.append(numero)

    session.commit()
    return {"comprados": len(comprados), "animais": comprados, "numero_lancamento": numero_lancamento}
